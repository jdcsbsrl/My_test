"""Export task list interactions for manual TEST/UAT slow regressions."""

import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError


class ExportTaskPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def row(self, task_name: str):
        return self.page.locator("tr").filter(has_text=task_name).first

    def wait_for_success(self, task_name: str, timeout_ms: int | None = None) -> str:
        if timeout_ms is None:
            timeout_ms = int(os.getenv("EXPORT_TASK_TIMEOUT_MS", "300000"))
        if timeout_ms < 10000:
            raise ValueError("EXPORT_TASK_TIMEOUT_MS must be at least 10000")
        poll_interval_ms = int(os.getenv("EXPORT_TASK_POLL_INTERVAL_MS", "3000"))
        if poll_interval_ms < 1000 or poll_interval_ms > 30000:
            raise ValueError("EXPORT_TASK_POLL_INTERVAL_MS must be between 1000 and 30000")
        deadline = time.monotonic() + timeout_ms / 1000
        search_input = self.page.locator('input[placeholder="请输入任务名称"]')
        search_button = self.page.locator('button:visible:has-text("搜索"), button:visible:has-text("查询")').first
        last_query: dict[str, object] = {
            "http": None,
            "code": None,
            "total": None,
            "rows": None,
            "matching_rows": None,
            "query_task_name": None,
        }
        while time.monotonic() <= deadline:
            remaining_ms = max(1000, int((deadline - time.monotonic()) * 1000))
            if search_input.count() and search_button.count():
                search_input.fill(task_name)
                try:
                    with self.page.expect_response(
                        lambda response: "/base/exportTask/list" in response.url,
                        timeout=min(5000, remaining_ms),
                    ) as response_event:
                        search_button.click()
                    response = response_event.value
                    try:
                        payload = response.json()
                    except Exception:
                        payload = {}
                    data = payload.get("data") if isinstance(payload, dict) else None
                    rows = payload.get("rows") if isinstance(payload, dict) else None
                    if rows is None and isinstance(data, dict):
                        rows = data.get("rows")
                    rows = rows if isinstance(rows, list) else []
                    total = payload.get("total") if isinstance(payload, dict) else None
                    if total is None and isinstance(data, dict):
                        total = data.get("total")
                    query = parse_qs(urlsplit(response.url).query)
                    last_query = {
                        "http": response.status,
                        "code": payload.get("code") if isinstance(payload, dict) else None,
                        "total": total,
                        "rows": len(rows),
                        "matching_rows": sum(1 for item in rows if task_name in str(item)),
                        "query_task_name": query.get("taskName"),
                    }
                except PlaywrightTimeoutError:
                    # Some task-list versions filter already loaded rows in the browser.
                    pass
            else:
                self.page.reload(wait_until="domcontentloaded")
            row = self.row(task_name)
            if row.count():
                state = row.inner_text()
                if "成功" in state:
                    return state
                if "失败" in state:
                    raise AssertionError(f"Export task failed: {task_name}: {state}")
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms > 0:
                self.page.wait_for_timeout(min(poll_interval_ms, remaining_ms))
        raise TimeoutError(f"Export task did not finish: {task_name}; last task-list query={last_query}")

    def download(self, task_name: str, destination: Path) -> Path:
        self.wait_for_success(task_name)
        with self.page.expect_download(timeout=120000) as download_info:
            self.row(task_name).get_by_text("下载", exact=True).click()
        download_info.value.save_as(str(destination))
        return destination

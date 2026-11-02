"""Export task list interactions for manual TEST/UAT slow regressions."""

import os
from pathlib import Path

from playwright.sync_api import Page


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
        elapsed = 0
        while elapsed <= timeout_ms:
            row = self.row(task_name)
            if row.count() == 0:
                self.page.wait_for_timeout(2000)
                if row.count() > 0:
                    continue
                self.page.wait_for_timeout(10000)
                elapsed += 10000
                self.page.reload(wait_until="domcontentloaded")
                self.page.wait_for_timeout(2000)
                continue
            state = row.inner_text()
            if "成功" in state:
                return state
            if "失败" in state:
                raise AssertionError(f"Export task failed: {task_name}: {state}")
            self.page.wait_for_timeout(10000)
            elapsed += 10000
            self.page.reload(wait_until="domcontentloaded")
        raise TimeoutError(f"Export task did not finish: {task_name}")

    def download(self, task_name: str, destination: Path) -> Path:
        self.wait_for_success(task_name)
        with self.page.expect_download(timeout=120000) as download_info:
            self.row(task_name).get_by_text("下载", exact=True).click()
        download_info.value.save_as(str(destination))
        return destination

"""Daily, read-only comparison of production ERP and public 17TRACK pages."""

from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import random
import re
import shutil
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from modules.auto_test.core.logistics_tracking_compare import (
    SAMPLE_SIZE,
    assess,
    query_candidates,
    render_report,
    write_manual_sheet,
)

ZONE = ZoneInfo("Asia/Shanghai")
LOGIN_PAGE = "https://erp.dayoneerp.com/oms-prod-ui/login"
LOGIN_API = "https://erp.dayoneerp.com/oms-prod-api/oms-admin/auth/login"
TRACK_PAGE = "https://t.17track.net/en"
STATUSES = ("ND", "DD", "AD", "NF")
TRACK_STATUSES = frozenset(
    {
        "Not found",
        "Info received",
        "In transit",
        "Pick up",
        "Out for Delivery",
        "Undelivered",
        "Delivered",
        "Alert",
        "Expired",
    }
)
FAMILIES = (
    "云途",
    "联邮通",
    "燕文",
    "美国专线",
    "急速",
    "顺丰",
    "中通",
    "圆通",
    "申通",
    "韵达",
    "极兔",
    "菜鸟",
    "DHL",
    "UPS",
    "FedEx",
    "USPS",
    "CNE",
    "4PX",
)
EVENT_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?$")


class TrackingBlockedError(RuntimeError):
    """The public page needs human attention or failed to return real data."""


def carrier_family(channel: str) -> str:
    name = channel.strip()
    for prefix in FAMILIES:
        if name.casefold().startswith(prefix.casefold()):
            return prefix
    return re.split(r"[-（( ]", name, maxsplit=1)[0] or "未命名渠道"


def _allow_login_only(route: object) -> None:
    request = route.request
    parsed = urlsplit(request.url)
    if parsed.scheme != "https" or parsed.hostname != "erp.dayoneerp.com":
        route.abort()
    elif request.url == LOGIN_API and request.method == "POST":
        route.continue_()
    elif parsed.path.startswith("/oms-prod-ui/") and request.method == "GET":
        route.continue_()
    else:
        route.abort()


def login_session(username: str, password: str, *, browser_path: str | None = None) -> requests.Session:
    """Use the permitted login page/API, keeping credentials and token in memory."""
    if not username or not password:
        raise ValueError("ERP production credentials are missing")
    with sync_playwright() as playwright:
        launch_args = {"headless": True}
        if browser_path:
            launch_args["executable_path"] = browser_path
        browser = playwright.chromium.launch(**launch_args)
        try:
            context = browser.new_context()
            context.route("**/*", _allow_login_only)
            page = context.new_page()
            page.goto(LOGIN_PAGE, wait_until="domcontentloaded", timeout=30000)
            account = page.locator("input[type='text']:visible")
            secret = page.locator("input[type='password']:visible")
            button = page.locator("button:visible")
            account.first.wait_for(state="visible", timeout=15000)
            if account.count() != 1 or secret.count() != 1 or button.count() != 1:
                raise RuntimeError("ERP login form changed")
            account.fill(username)
            secret.fill(password)
            with page.expect_response(
                lambda result: result.url == LOGIN_API and result.request.method == "POST",
                timeout=30000,
            ) as event:
                button.click()
            response = event.value
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            data = data if isinstance(data, dict) else {}
            token = data.get("token") or data.get("access_token")
            clientid = response.request.headers.get("clientid")
            if response.status != 200 or body.get("code") != 200 or not token or not clientid:
                raise RuntimeError("ERP login failed; listNew was not called")
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {token}",
                    "clientid": clientid,
                    "Content-Type": "application/json",
                }
            )
            return session
        finally:
            browser.close()


def query_strata(session: requests.Session, day: date) -> tuple[list[dict[str, str]], list[str]]:
    """Scan fixed, bounded date/status strata through listNew only."""
    windows = (
        ("较早", day - timedelta(days=90), day - timedelta(days=30)),
        ("较近", day - timedelta(days=29), day - timedelta(days=7)),
    )
    all_rows: list[dict[str, str]] = []
    scope: list[str] = []
    for label, first_day, last_day in windows:
        begin = f"{first_day:%Y-%m-%d} 00:00:00"
        end = f"{last_day:%Y-%m-%d} 23:59:59"
        for code in STATUSES:
            for attempt in range(3):
                try:
                    rows, truncated = query_candidates(
                        session,
                        max_pages=1,
                        logistics_date_begin=begin,
                        logistics_date_end=end,
                        tracking_status_list=[code],
                    )
                    break
                except (requests.RequestException, RuntimeError) as exc:
                    if attempt == 2:
                        scope.append(f"{label} {first_day}至{last_day} {code} 查询失败：{type(exc).__name__}")
                    else:
                        time.sleep(2)
            else:
                continue
            for row in rows:
                all_rows.append({**row, "_window": label})
            scope.append(
                f"{label} {first_day}至{last_day} {code}: 第1页、合格{len(rows)}单、"
                f"{'仍有后续页' if truncated else '已到末页'}"
            )
    return all_rows, scope


def load_used_hashes(root: Path, archive: Path) -> set[str]:
    public_ci = os.environ.get("ERP_17TRACK_PUBLIC_CI") == "1"
    key = os.environ.get("ERP_17TRACK_HISTORY_KEY", "")
    if public_ci and len(key) < 32:
        raise ValueError("Public CI requires a history HMAC key of at least 32 characters")
    scheme = "hmac-sha256" if key else "sha256"
    used: set[str] = set()
    seed = os.environ.get("ERP_17TRACK_PRIOR_HASHES", "")
    for item in re.split(r"[,\s]+", seed.strip()):
        if not item:
            continue
        if not re.fullmatch(r"[a-f0-9]{64}", item):
            raise ValueError("Invalid prior tracking hash seed")
        used.add(item)
    history = archive / "history.json"
    if archive.exists() and not history.exists() and any(archive.iterdir()):
        raise ValueError("Nonempty history artifact is missing history.json")
    if history.exists():
        body = json.loads(history.read_text(encoding="utf-8"))
        if body.get("version") != 1 or not isinstance(body.get("used_sha256"), list):
            raise ValueError("History artifact has an unknown format")
        if body.get("hash_scheme", "sha256") != scheme:
            raise ValueError("History hash scheme does not match the configured key")
        used.update(body["used_sha256"])
    private = root / "data/private"
    for path in private.glob("logistics_tracking_*.csv"):
        with path.open(newline="", encoding="utf-8-sig") as stream:
            for row in csv.DictReader(stream):
                number = row.get("tracking_number", "").strip()
                if number:
                    used.add(number_hash(number))
    return used


def number_hash(number: str) -> str:
    key = os.environ.get("ERP_17TRACK_HISTORY_KEY", "")
    if key:
        return hmac.new(key.encode("utf-8"), number.encode("utf-8"), hashlib.sha256).hexdigest()
    return hashlib.sha256(number.encode("utf-8")).hexdigest()


def choose_samples(
    candidates: list[dict[str, str]],
    used_hashes: set[str],
    day: date,
) -> list[dict[str, str]]:
    """Prioritize status and carrier diversity, then older unresolved parcels."""
    shuffled = list(candidates)
    random.Random(f"{day.isoformat()}-daily").shuffle(shuffled)
    available = [row for row in shuffled if number_hash(row["tracking_number"]) not in used_hashes]
    selected: list[dict[str, str]] = []
    used_numbers: set[str] = set()
    used_families: set[str] = set()
    used_channels: set[str] = set()

    def add(row: dict[str, str]) -> None:
        selected.append(row)
        used_numbers.add(row["tracking_number"])
        used_families.add(carrier_family(row["provider_channel_name"]))
        used_channels.add(row["provider_channel_name"])

    for code in STATUSES:
        options = [
            row for row in available if row["erp_status_code"] == code and row["tracking_number"] not in used_numbers
        ]
        options.sort(
            key=lambda row: (
                carrier_family(row["provider_channel_name"]) in used_families,
                row["_window"] != "较早",
                row["erp_latest_tracking_time"],
            )
        )
        if options:
            add(options[0])
    for row in sorted(
        available,
        key=lambda item: (
            carrier_family(item["provider_channel_name"]) in used_families,
            item["provider_channel_name"] in used_channels,
            item["_window"] != "较早",
            item["erp_latest_tracking_time"],
        ),
    ):
        if len(selected) == SAMPLE_SIZE:
            break
        if row["tracking_number"] not in used_numbers:
            add(row)
    return [{key: value for key, value in row.items() if not key.startswith("_")} for row in selected]


def parse_summary(number: str, summary: str) -> tuple[str, str, str]:
    """Parse the visible 17TRACK result card; reject unknown layouts."""
    lines = [line.strip() for line in summary.splitlines() if line.strip()]
    if len(lines) < 6 or lines[0] != number:
        raise TrackingBlockedError(f"17TRACK result card missing for {number}")
    status = next((item for item in TRACK_STATUSES if lines[1].startswith(item + " ") or lines[1] == item), None)
    times = [index for index, line in enumerate(lines) if EVENT_TIME.fullmatch(line)]
    if status is None or len(times) != 1 or times[0] + 1 >= len(lines):
        raise TrackingBlockedError(f"17TRACK result card changed for {number}")
    event_index = times[0]
    carrier = lines[3] if event_index >= 5 else "未识别承运商"
    return status, lines[event_index], f"{carrier}; {lines[event_index + 1]}"


def track_public(rows: list[dict[str, str]], *, browser_path: str | None = None) -> None:
    """Query the public webpage in a real browser; never call a 17TRACK API directly."""
    numbers = [row["tracking_number"] for row in rows]
    if not numbers or len(numbers) > SAMPLE_SIZE or len(set(numbers)) != len(numbers):
        raise ValueError("Expected up to ten distinct tracking numbers")
    with sync_playwright() as playwright:
        launch_args = {"headless": True}
        if browser_path:
            launch_args["executable_path"] = browser_path
        browser = playwright.chromium.launch(**launch_args)
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto(
                TRACK_PAGE + "#nums=" + ",".join(numbers),
                wait_until="domcontentloaded",
                timeout=30000,
            )
            entry = page.locator("textarea[placeholder^='Enter up to 40 numbers']")
            entry.wait_for(state="visible", timeout=30000)
            page.wait_for_function(
                """number => [...document.querySelectorAll('textarea')].some(
                  x => x.value.includes(number))""",
                arg=numbers[0],
                timeout=30000,
            )
            # The page replaces its first rendered form while loading demo data.
            # Wait for the demo card so our input/click survives hydration.
            page.get_by_text("TestNumber00017", exact=True).first.wait_for(timeout=30000)
            page.wait_for_timeout(8000)
            tour = page.locator("#react-joyride-portal button:visible")
            if tour.count():
                tour.first.click()
            entry.fill("\n".join(numbers))
            page.locator("button[title*=TRACK]:visible").click(timeout=15000)
            try:
                page.wait_for_function(
                    """nums => nums.every(n => [...document.querySelectorAll(
                      'span.text-sm.font-medium.truncate')].some(x => x.textContent.trim() === n))""",
                    arg=numbers,
                    timeout=90000,
                )
            except PlaywrightTimeoutError as exc:
                visible = page.locator("body").inner_text().casefold()
                reason = (
                    "验证码或访问限制"
                    if any(term in visible for term in ("captcha", "verify you", "access denied", "unusual traffic"))
                    else "未返回全部真实运单"
                )
                raise TrackingBlockedError(f"17TRACK {reason}; 已停止自动交互") from exc
            checked_at = datetime.now(ZONE).strftime("%Y-%m-%d %H:%M:%S %z")
            for row in rows:
                number = row["tracking_number"]
                card = page.locator("span.text-sm.font-medium.truncate").filter(
                    has_text=re.compile(rf"^{re.escape(number)}$")
                )
                if card.count() != 1:
                    raise TrackingBlockedError(f"17TRACK duplicate/missing card for {number}")
                deadline = time.monotonic() + 45
                while True:
                    summary = card.evaluate("""x => {
                        for (let i = 0; i < 5; i++) x = x.parentElement;
                        return x.innerText;
                    }""")
                    try:
                        status, latest_time, notes = parse_summary(number, summary)
                        break
                    except TrackingBlockedError:
                        if time.monotonic() >= deadline:
                            raise
                        page.wait_for_timeout(1000)
                row["track17_status"] = status
                row["track17_latest_time"] = latest_time
                row["track17_checked_at"] = checked_at
                row["notes"] = notes
        finally:
            browser.close()


def save_results(
    root: Path,
    archive: Path,
    day: date,
    rows: list[dict[str, str]],
    scope: list[str],
    used_hashes: set[str],
    error: str = "",
) -> tuple[Path, Path]:
    run_id = uuid.uuid4().hex[:8]
    private_sheet = root / "data/private" / f"logistics_tracking_{day:%Y%m%d}_{run_id}.csv"
    write_manual_sheet(private_sheet, rows)
    details = "; ".join(scope)
    details += f"；排除历史样本{len(used_hashes)}单；样本{len(rows)}单，"
    details += f"覆盖{len({row['provider_channel_name'] for row in rows})}个ERP渠道。"
    report = render_report(day, rows, scope=details)
    if error:
        report += f"\n\n本次采集失败：{error}。未完成行不得判为一致。\n"
    report += "\n时间说明：ERP 与 17TRACK 事件时间按各自来源原样记录；网页事件时区未确认，不能直接计算精确同步延迟。\n"
    report_path = root / "workspace" / f"{day:%Y%m%d}" / f"物流轨迹17TRACK抽查报告_{run_id}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    if not error and len(rows) == SAMPLE_SIZE and all(row["track17_status"] for row in rows):
        history = archive / "history.json"
        archive.mkdir(parents=True, exist_ok=True)
        used_hashes.update(number_hash(row["tracking_number"]) for row in rows)
        history.write_text(
            json.dumps(
                {
                    "version": 1,
                    "hash_scheme": "hmac-sha256" if os.environ.get("ERP_17TRACK_HISTORY_KEY") else "sha256",
                    "used_sha256": sorted(used_hashes),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        if os.environ.get("ERP_17TRACK_PUBLIC_CI") == "1":
            return report_path, private_sheet
        archived_report = archive / "reports" / f"{day:%Y%m%d}" / report_path.name
        archived_sheet = archive / "private" / f"{day:%Y%m%d}" / private_sheet.name
        archived_report.parent.mkdir(parents=True, exist_ok=True)
        archived_sheet.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(report_path, archived_report)
        shutil.copy2(private_sheet, archived_sheet)
    return report_path, private_sheet


def verdict_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    return dict(Counter(row["verdict"] for row in assess(rows)))

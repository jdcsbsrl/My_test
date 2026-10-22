"""Read-only ERP logistics sampling and public 17TRACK comparison."""

from __future__ import annotations

import csv
import random
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import requests

ERP_LIST_URL = "https://erp.dayoneerp.com/oms-prod-api/oms-admin/" "system/salesOrderLogisticsTracking/listNew"
PAGE_SIZE = 20
SAMPLE_SIZE = 10
EXCLUDED_CODES = frozenset({"AF", "CC"})
EXPECTED_STATUS = {
    "NO": "Not found",
    "ND": "In transit",
    "PU": "Pick up",
    "DD": "Out for Delivery",
    "AD": "Undelivered",
    "NF": "Alert",
    "ED": "Expired",
}
STATUS_ALIASES = {
    "notfound": "Not found",
    "inforeceived": "Info received",
    "intransit": "In transit",
    "availableforpickup": "Pick up",
    "pickup": "Pick up",
    "outfordelivery": "Out for Delivery",
    "deliveryfailure": "Undelivered",
    "undelivered": "Undelivered",
    "delivered": "Delivered",
    "exception": "Alert",
    "alert": "Alert",
    "expired": "Expired",
}
STATUS_NAMES = {
    "Not found": "查询不到",
    "Info received": "收到信息",
    "In transit": "运输途中",
    "Pick up": "到达待取",
    "Out for Delivery": "派送途中",
    "Undelivered": "投递失败",
    "Delivered": "成功签收",
    "Alert": "可能异常",
    "Expired": "运输过久",
}
PROGRESS_RANK = {
    "Not found": 0,
    "Info received": 1,
    "In transit": 2,
    "Pick up": 3,
    "Out for Delivery": 3,
    "Delivered": 4,
}
CSV_FIELDS = (
    "tracking_number",
    "provider_channel_name",
    "erp_status_code",
    "erp_status_name",
    "erp_latest_tracking_time",
    "erp_last_crawl_time",
    "track17_status",
    "track17_latest_time",
    "track17_checked_at",
    "notes",
)


class LogisticsQueryError(RuntimeError):
    """The permitted ERP read failed or returned an unknown contract."""


def build_payload(
    page_number: int,
    *,
    logistics_date_begin: str | None = None,
    logistics_date_end: str | None = None,
    tracking_status_list: list[str] | None = None,
) -> dict[str, Any]:
    if page_number < 1:
        raise ValueError("page_number must be positive")
    status_list = tracking_status_list or []
    if any(code not in EXPECTED_STATUS for code in status_list):
        raise ValueError("tracking_status_list contains an excluded or unknown status")
    return {
        "storeIdSet": [],
        "onlyDotTrackingNo": False,
        "trackingStatusList": status_list,
        "payTimeBeginStr": None,
        "payTimeEndStr": None,
        "logisticsDateBeginStr": logistics_date_begin,
        "logisticsDateEndStr": logistics_date_end,
        "orderNo": "",
        "trackingNumber": "",
        "pageNum": page_number,
        "pageSize": PAGE_SIZE,
    }


def _extract_rows(body: Any) -> list[dict[str, Any]]:
    if isinstance(body, list):
        rows = body
    elif isinstance(body, dict):
        if body.get("code") not in (None, 0, "0", 200, "200"):
            raise LogisticsQueryError("ERP returned a business error")
        container = body.get("data", body)
        if isinstance(container, list):
            rows = container
        elif isinstance(container, dict):
            rows = next(
                (
                    container[key]
                    for key in ("records", "list", "rows", "items")
                    if isinstance(container.get(key), list)
                ),
                None,
            )
        else:
            rows = None
    else:
        rows = None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise LogisticsQueryError("Unrecognized ERP list response shape")
    return rows


def query_candidates(
    session: requests.Session,
    *,
    max_pages: int = 10,
    logistics_date_begin: str | None = None,
    logistics_date_end: str | None = None,
    tracking_status_list: list[str] | None = None,
) -> tuple[list[dict[str, str]], bool]:
    """POST only the exact approved list URL; return eligible rows and truncation flag."""
    if not 1 <= max_pages <= 20:
        raise ValueError("max_pages must be between 1 and 20")
    candidates: dict[tuple[str, str], dict[str, str]] = {}
    seen_pages: set[tuple[str, ...]] = set()
    for page_number in range(1, max_pages + 1):
        response = session.post(
            ERP_LIST_URL,
            json=build_payload(
                page_number,
                logistics_date_begin=logistics_date_begin,
                logistics_date_end=logistics_date_end,
                tracking_status_list=tracking_status_list,
            ),
            timeout=(10, 60),
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise LogisticsQueryError(f"ERP HTTP {response.status_code}; query stopped")
        try:
            rows = _extract_rows(response.json())
        except (ValueError, TypeError) as exc:
            raise LogisticsQueryError("ERP response is not valid JSON") from exc
        fingerprint = tuple(str(row.get("id", "")) for row in rows)
        if rows and fingerprint in seen_pages:
            raise LogisticsQueryError("ERP pagination repeated a page")
        seen_pages.add(fingerprint)
        for row in rows:
            code = str(row.get("trackingStatus") or "").strip().upper()
            number = str(row.get("trackingNumber") or "").strip()
            carrier_id = str(row.get("providerChannelId") or "").strip()
            if code in EXCLUDED_CODES or not number or code not in EXPECTED_STATUS:
                continue
            candidates[(number, carrier_id)] = {
                "tracking_number": number,
                "provider_channel_name": str(row.get("providerChannelName") or ""),
                "erp_status_code": code,
                "erp_status_name": str(row.get("trackingStatusName") or ""),
                "erp_latest_tracking_time": str(row.get("latestTrackingTime") or ""),
                "erp_last_crawl_time": str(row.get("lastCrawlTime") or ""),
                "track17_status": "",
                "track17_latest_time": "",
                "track17_checked_at": "",
                "notes": "",
            }
        if len(rows) < PAGE_SIZE:
            return list(candidates.values()), False
    return list(candidates.values()), True


def select_samples(candidates: list[dict[str, str]], day: date) -> list[dict[str, str]]:
    """Select up to ten deterministic samples across statuses and channels."""
    shuffled = list(candidates)
    random.Random(day.isoformat()).shuffle(shuffled)
    selected: list[dict[str, str]] = []
    selected_numbers: set[str] = set()
    for code in EXPECTED_STATUS:
        match = next(
            (
                row
                for row in shuffled
                if row["erp_status_code"] == code and row["tracking_number"] not in selected_numbers
            ),
            None,
        )
        if match is not None:
            selected.append(match)
            selected_numbers.add(match["tracking_number"])
    selected_channels = {row["provider_channel_name"] for row in selected}
    for row in shuffled:
        if len(selected) == SAMPLE_SIZE:
            break
        channel = row["provider_channel_name"]
        if channel not in selected_channels and row["tracking_number"] not in selected_numbers:
            selected.append(row)
            selected_numbers.add(row["tracking_number"])
            selected_channels.add(channel)
    for row in shuffled:
        if len(selected) == SAMPLE_SIZE:
            break
        if row["tracking_number"] not in selected_numbers:
            selected.append(row)
            selected_numbers.add(row["tracking_number"])
    return selected


def write_manual_sheet(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def read_manual_sheet(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != CSV_FIELDS:
            raise ValueError("Manual sheet columns do not match the expected template")
        return list(reader)


def normalize_status(value: str) -> str | None:
    key = "".join(char for char in value.casefold() if char.isalnum())
    return STATUS_ALIASES.get(key)


def assess(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for row in rows:
        expected = EXPECTED_STATUS.get(row["erp_status_code"])
        observed = normalize_status(row["track17_status"])
        if expected is None or observed is None or not row["track17_checked_at"]:
            verdict = "未完成"
        elif observed == expected:
            verdict = "一致"
        elif observed == "Delivered" and expected != "Delivered":
            verdict = "系统落后（重点）"
        elif expected == "Out for Delivery" and observed == "Undelivered":
            verdict = "系统落后（重点）"
        elif expected in PROGRESS_RANK and observed in PROGRESS_RANK:
            if PROGRESS_RANK[expected] < PROGRESS_RANK[observed]:
                verdict = "系统落后（重点）"
            elif PROGRESS_RANK[expected] > PROGRESS_RANK[observed]:
                verdict = "提醒（系统超前）"
            else:
                verdict = "状态差异待复核"
        else:
            verdict = "状态差异待复核"
        results.append(
            {
                **row,
                "expected_status": expected or "",
                "observed_status": observed or "",
                "observed_status_name": STATUS_NAMES.get(observed or "", ""),
                "verdict": verdict,
            }
        )
    return results


def mask_number(number: str) -> str:
    return f"{number[:3]}***{number[-4:]}" if len(number) > 7 else "***"


def render_report(day: date, rows: list[dict[str, str]], *, scope: str = "") -> str:
    results = assess(rows)
    counts = Counter(row["verdict"] for row in results)
    complete = len(results) == SAMPLE_SIZE and not counts["未完成"]
    if not complete:
        conclusion = "验证不完整"
    elif counts["系统落后（重点）"]:
        conclusion = "发现系统落后于17TRACK的重点差异"
    elif counts["状态差异待复核"]:
        conclusion = "存在状态差异待复核"
    elif counts["提醒（系统超前）"]:
        conclusion = "存在系统超前提醒"
    else:
        conclusion = "全部一致"
    lines = [
        f"# 物流轨迹与17TRACK抽查报告（{day.isoformat()}）",
        "",
        f"结论：**{conclusion}**。样本 {len(results)}/{SAMPLE_SIZE}；一致 {counts['一致']}；"
        f"系统落后（重点）{counts['系统落后（重点）']}；提醒（系统超前）{counts['提醒（系统超前）']}；"
        f"其他差异 {counts['状态差异待复核']}；未完成 {counts['未完成']}。",
        "",
        (
            "ERP 来源：生产环境指定的 `salesOrderLogisticsTracking/listNew` 只读查询。"
            "17TRACK 状态来自公开网页批量查询。"
        ),
        *([f"抽样范围：{scope}"] if scope else []),
        "",
        (
            "判定口径：17TRACK 已进入更后续的物流阶段而 ERP 尚未到达，"
            "标为**系统落后（重点）**；17TRACK 已签收而 ERP 未签收优先列为重点。"
            "ERP 显示更后续阶段、17TRACK 仍处于较早阶段，标为**提醒（系统超前）**。"
            "17TRACK 已投递失败而 ERP 仍显示派送途中，也标为系统落后。"
            "其余异常类状态不可简单线性排序，单列待复核。"
        ),
        "",
        (
            "| 完整运单号 | 渠道 | ERP状态 | 17TRACK状态 | ERP最新事件时间 | "
            "ERP上次抓取 | 17TRACK最新事件时间 | 查询时间 | 判定 | 备注 |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    priority = {"系统落后（重点）": 0, "状态差异待复核": 1, "提醒（系统超前）": 2, "一致": 3, "未完成": 4}
    for row in sorted(results, key=lambda item: priority[item["verdict"]]):
        cells = [
            row["tracking_number"],
            row["provider_channel_name"],
            f"{row['erp_status_name'] or row['erp_status_code']}（{row['erp_status_code']}）",
            f"{row['observed_status_name']}（{row['observed_status']}）" if row["observed_status"] else "未取得",
            row["erp_latest_tracking_time"],
            row["erp_last_crawl_time"],
            row["track17_latest_time"],
            row["track17_checked_at"],
            row["verdict"],
            row["notes"],
        ]
        lines.append("| " + " | ".join(str(value).replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    lines += ["", "系统落后项应优先核对承运商、17TRACK事件时间与 ERP 抓取时间；首次差异需复核，不直接认定为缺陷。", ""]
    return "\n".join(lines)

"""Send an ERP/17TRACK report directly to the owner's mailbox."""

from __future__ import annotations

import smtplib
import ssl
from collections import Counter
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from modules.auto_test.core.logistics_tracking_compare import assess, read_manual_sheet
from modules.auto_test.core.logistics_tracking_daily import ZONE


def latest_result(root: Path) -> tuple[Path | None, Path | None]:
    """Find the report and matching private CSV created on this runner."""
    reports = sorted(
        (root / "workspace").glob("*/物流轨迹17TRACK抽查报告_*.md"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for report in reports:
        run_id = report.stem.rsplit("_", 1)[-1]
        sheet = root / "data/private" / f"logistics_tracking_{report.parent.name}_{run_id}.csv"
        if sheet.is_file():
            return report, sheet
    return None, None


def build_message(
    address: str,
    report: Path | None,
    sheet: Path | None,
    *,
    run_url: str = "",
) -> EmailMessage:
    """Create a full-detail email without printing its content to Actions logs."""
    rows = assess(read_manual_sheet(sheet)) if report and sheet else []
    counts = Counter(row["verdict"] for row in rows)
    complete = len(rows) == 10 and not counts["未完成"]
    day = datetime.now(ZONE).strftime("%Y-%m-%d")
    if not complete:
        outcome = "抽查未完成"
    elif counts["系统落后（重点）"] or counts["状态差异待复核"] or counts["提醒（系统超前）"]:
        outcome = "发现状态差异"
    else:
        outcome = "全部一致"
    message = EmailMessage()
    message["From"] = address
    message["To"] = address
    message["Subject"] = f"[ERP物流轨迹] {day} {outcome}：系统落后{counts['系统落后（重点）']}单"
    lines = [
        f"ERP 与 17TRACK 每日轨迹抽查：{outcome}",
        f"样本 {len(rows)}/10；系统落后 {counts['系统落后（重点）']}；"
        f"系统超前提醒 {counts['提醒（系统超前）']}；一致 {counts['一致']}；"
        f"待复核 {counts['状态差异待复核']}；未完成 {counts['未完成']}。",
    ]
    if run_url:
        lines.append(f"Actions 运行：{run_url}")
    lines.extend(["", "差异明细："])
    priority = {"系统落后（重点）": 0, "状态差异待复核": 1, "提醒（系统超前）": 2, "未完成": 3}
    differences = sorted(
        (row for row in rows if row["verdict"] != "一致"),
        key=lambda row: (priority.get(row["verdict"], 9), row["tracking_number"]),
    )
    for index, row in enumerate(differences, 1):
        lines.extend(
            [
                f"{index}. {row['verdict']}｜{row['tracking_number']}｜{row['provider_channel_name']}",
                f"   ERP：{row['erp_status_name']}（{row['erp_status_code']}），"
                f"事件 {row['erp_latest_tracking_time']}，抓取 {row['erp_last_crawl_time']}",
                f"   17TRACK：{row['observed_status_name'] or '未取得'}"
                f"（{row['observed_status'] or '-'}），事件 {row['track17_latest_time'] or '-'}，"
                f"查询 {row['track17_checked_at'] or '-'}",
            ]
        )
    if not differences:
        lines.append("没有状态差异；如本次未完成，请查看 Actions 运行记录。")
    lines.extend(["", "附件为完整内部报告；差异需核对原始事件和时区，不直接认定为缺陷。"])
    message.set_content("\n".join(lines), charset="utf-8")
    if report and report.is_file():
        message.add_attachment(
            report.read_text(encoding="utf-8"),
            subtype="markdown",
            filename=report.name,
        )
    return message


def send_qq_message(message: EmailMessage, address: str, authorization_code: str) -> None:
    """Use QQ's TLS-protected SMTP submission; no credential is logged."""
    if not authorization_code:
        raise ValueError("QQ SMTP authorization code is missing")
    with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=25, context=ssl.create_default_context()) as smtp:
        smtp.login(address, authorization_code)
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError("SMTP refused one or more recipients")

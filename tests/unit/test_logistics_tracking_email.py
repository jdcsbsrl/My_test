"""Offline checks for private report delivery."""

from datetime import date

from modules.auto_test.core.logistics_tracking_daily import save_results
from modules.auto_test.core.logistics_tracking_email import build_message, latest_result


def test_complete_email_contains_full_difference_and_report_attachment(tmp_path):
    rows = [
        {
            "tracking_number": f"TEST{index:04d}",
            "provider_channel_name": "样本渠道",
            "erp_status_code": "ND",
            "erp_status_name": "运输途中",
            "erp_latest_tracking_time": "2026-10-08 01:00:00",
            "erp_last_crawl_time": "2026-10-09 01:00:00",
            "track17_status": "Delivered",
            "track17_latest_time": "2026-10-09 02:00",
            "track17_checked_at": "2026-10-09 15:31:00 +0800",
            "notes": "sample evidence",
        }
        for index in range(10)
    ]
    report, sheet = save_results(tmp_path, tmp_path / "archive", date(2026, 10, 9), rows, [], set())
    assert latest_result(tmp_path) == (report, sheet)
    message = build_message("owner@qq.com", report, sheet)
    assert "系统落后10单" in message["Subject"]
    assert "TEST0000" in message.get_body(preferencelist=("plain",)).get_content()
    attachments = list(message.iter_attachments())
    assert len(attachments) == 1
    assert "TEST0009" in attachments[0].get_content()


def test_incomplete_email_has_no_attachment():
    message = build_message("owner@qq.com", None, None)
    assert "抽查未完成" in message["Subject"]
    assert list(message.iter_attachments()) == []

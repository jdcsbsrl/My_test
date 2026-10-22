"""Meaningful offline checks for the independent daily tracking runner."""

from datetime import date
import json

import pytest

from modules.auto_test.core import logistics_tracking_daily
from modules.auto_test.core.logistics_tracking_daily import (
    LOGIN_API,
    TrackingBlockedError,
    _allow_login_only,
    choose_samples,
    load_used_hashes,
    number_hash,
    parse_summary,
    save_results,
)
from tools.run_logistics_tracking_daily import _safe_failure


def test_query_strata_retries_transient_failure_and_limits_each_status_to_first_page(monkeypatch):
    calls = []

    def query(_session, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise RuntimeError("temporary business error")
        return [], True

    monkeypatch.setattr(logistics_tracking_daily, "query_candidates", query)
    monkeypatch.setattr(logistics_tracking_daily.time, "sleep", lambda _seconds: None)
    rows, scope = logistics_tracking_daily.query_strata(object(), date(2026, 10, 10))
    assert rows == []
    assert len(calls) == 9
    assert len(scope) == 8
    assert all(call["max_pages"] == 1 for call in calls)
    assert all("第1页" in item for item in scope)


def test_parse_result_card_and_reject_demo_card():
    summary = (
        "TEST-4PX-0001\nPick up (23 Days)\nChina\n4PX\n"
        "United Kingdom\n2026-09-26 06:08\nGB, Available for Redelivery or Collection"
    )
    assert parse_summary("TEST-4PX-0001", summary) == (
        "Pick up",
        "2026-09-26 06:08",
        "4PX; GB, Available for Redelivery or Collection",
    )
    with pytest.raises(TrackingBlockedError):
        parse_summary("TEST-4PX-0001", summary.replace("TEST-4PX-0001", "TestNumber00017"))


def test_browser_route_blocks_every_other_production_api():
    class Request:
        def __init__(self, url, method):
            self.url = url
            self.method = method

    class Route:
        def __init__(self, url, method):
            self.request = Request(url, method)
            self.action = ""

        def abort(self):
            self.action = "abort"

        def continue_(self):
            self.action = "continue"

    for url, method, expected in (
        (LOGIN_API, "POST", "continue"),
        (LOGIN_API, "GET", "abort"),
        ("https://erp.dayoneerp.com/oms-prod-ui/login", "GET", "continue"),
        ("https://erp.dayoneerp.com/oms-prod-api/oms-admin/other", "POST", "abort"),
        ("https://erp.dayoneerp.com/other-api/read", "GET", "abort"),
        ("https://example.com/anything", "GET", "abort"),
    ):
        route = Route(url, method)
        _allow_login_only(route)
        assert route.action == expected


def test_sampling_keeps_ten_unique_new_numbers_and_status_coverage():
    candidates = []
    for index in range(24):
        candidates.append(
            {
                "tracking_number": f"TEST{index:04d}",
                "provider_channel_name": f"渠道{index % 10}",
                "erp_status_code": ("ND", "DD", "AD", "NF")[index % 4],
                "erp_latest_tracking_time": f"2026-09-{index % 20 + 1:02d} 01:00:00",
                "_window": "较早" if index < 12 else "较近",
            }
        )
    used = {number_hash("TEST0000"), number_hash("TEST0001")}
    selected = choose_samples(candidates, used, date(2026, 10, 9))
    assert len(selected) == len({row["tracking_number"] for row in selected}) == 10
    assert "TEST0000" not in {row["tracking_number"] for row in selected}
    assert "TEST0001" not in {row["tracking_number"] for row in selected}
    assert {row["erp_status_code"] for row in selected} == {"ND", "DD", "AD", "NF"}
    assert all("_window" not in row for row in selected)


def test_complete_report_archives_history_without_committing_data(tmp_path):
    rows = []
    for index in range(10):
        rows.append(
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
        )
    archive = tmp_path / ".runtime/cache/logistics_tracking_archive"
    report, sheet = save_results(tmp_path, archive, date(2026, 10, 9), rows, ["mock scope"], set())
    assert report.exists() and sheet.exists()
    assert "TEST0000" in report.read_text(encoding="utf-8")
    assert (archive / "history.json").exists()
    assert len(list((archive / "reports/20261009").glob("*.md"))) == 1
    assert len(list((archive / "private/20261009").glob("*.csv"))) == 1


def test_nonempty_archive_without_manifest_stops_dedup(tmp_path):
    archive = tmp_path / "archive"
    archive.mkdir()
    (archive / "reports").mkdir()
    with pytest.raises(ValueError, match="history.json"):
        load_used_hashes(tmp_path, archive)


def test_public_ci_requires_key_and_archives_only_hmac_history(tmp_path, monkeypatch):
    monkeypatch.setenv("ERP_17TRACK_PUBLIC_CI", "1")
    with pytest.raises(ValueError, match="HMAC key"):
        load_used_hashes(tmp_path, tmp_path / "archive")
    monkeypatch.setenv("ERP_17TRACK_HISTORY_KEY", "a" * 40)
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
    archive = tmp_path / ".runtime/cache/logistics_tracking_archive"
    report, sheet = save_results(tmp_path, archive, date(2026, 10, 9), rows, [], set())
    assert report.exists() and sheet.exists()
    assert sorted(path.name for path in archive.rglob("*")) == ["history.json"]
    history = json.loads((archive / "history.json").read_text(encoding="utf-8"))
    assert history["hash_scheme"] == "hmac-sha256"
    assert "TEST0000" not in (archive / "history.json").read_text(encoding="utf-8")
    assert number_hash("TEST0000") in load_used_hashes(tmp_path, archive)


def test_failure_summary_exposes_only_safe_page_stage():
    error = TrackingBlockedError("private tracking number TEST0000", public_stage="等待真实运单结果超时")
    summary = _safe_failure(error)
    assert "等待真实运单结果超时" in summary
    assert "TEST0000" not in summary

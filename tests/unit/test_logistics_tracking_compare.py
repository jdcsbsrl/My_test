from __future__ import annotations

from datetime import date

from modules.auto_test.core.logistics_tracking_compare import (
    ERP_LIST_URL,
    assess,
    build_payload,
    query_candidates,
    render_report,
    select_samples,
)


class _Response:
    status_code = 200

    def __init__(self, body):
        self.body = body

    def json(self):
        return self.body


class _Session:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(self.body)


def test_only_approved_list_endpoint_is_called_and_filter_uses_status_code():
    session = _Session(
        {
            "code": 200,
            "data": {
                "records": [
                    {
                        "trackingNumber": "TRACK-A",
                        "providerChannelId": "4PX",
                        "trackingStatus": "ND",
                        "trackingStatusName": "运输途中",
                        "latestLogisticsInformation": "Parcel information received",
                    },
                    {"trackingNumber": "TRACK-B", "providerChannelId": "4PX", "trackingStatus": "AF"},
                    {"trackingNumber": "TRACK-C", "providerChannelId": "4PX", "trackingStatus": "CC"},
                ]
            },
        }
    )
    rows, truncated = query_candidates(session)
    assert not truncated
    assert [row["tracking_number"] for row in rows] == ["TRACK-A"]
    assert session.calls == [
        (
            ERP_LIST_URL,
            {
                "json": build_payload(1),
                "timeout": (10, 60),
                "allow_redirects": False,
            },
        )
    ]


def test_status_filter_rejects_excluded_code():
    assert build_payload(1, tracking_status_list=["ND"])["trackingStatusList"] == ["ND"]
    try:
        build_payload(1, tracking_status_list=["AF"])
    except ValueError:
        pass
    else:
        raise AssertionError("AF must not be queried")


def test_sample_prefers_distinct_statuses_and_limits_to_ten():
    rows = [
        {"tracking_number": f"NUMBER-{i}", "erp_status_code": code, "provider_channel_name": f"CARRIER-{i % 3}"}
        for i, code in enumerate(["ND"] * 16 + ["NO", "PU", "DD", "AD", "NF", "ED"])
    ]
    selected = select_samples(rows, date(2026, 10, 7))
    assert len(selected) == 10
    assert {row["erp_status_code"] for row in selected} == {"ND", "NO", "PU", "DD", "AD", "NF", "ED"}
    assert selected == select_samples(rows, date(2026, 10, 7))


def test_compare_uses_17track_web_status_and_marks_missing_evidence_incomplete():
    rows = [
        {
            "tracking_number": "NUMBER-1",
            "provider_channel_name": "Carrier",
            "erp_status_code": "PU",
            "erp_status_name": "到达待取",
            "erp_latest_tracking_time": "",
            "erp_last_crawl_time": "",
            "track17_status": "Pick up",
            "track17_latest_time": "",
            "track17_checked_at": "2026-10-07 14:00",
            "notes": "",
        },
        {
            "tracking_number": "NUMBER-2",
            "provider_channel_name": "Carrier",
            "erp_status_code": "ED",
            "erp_status_name": "运输过久",
            "erp_latest_tracking_time": "",
            "erp_last_crawl_time": "",
            "track17_status": "Alert",
            "track17_latest_time": "",
            "track17_checked_at": "2026-10-07 14:00",
            "notes": "",
        },
        {
            "tracking_number": "NUMBER-3",
            "provider_channel_name": "Carrier",
            "erp_status_code": "ND",
            "erp_status_name": "运输途中",
            "erp_latest_tracking_time": "",
            "erp_last_crawl_time": "",
            "track17_status": "",
            "track17_latest_time": "",
            "track17_checked_at": "",
            "notes": "",
        },
    ]
    assert [result["verdict"] for result in assess(rows)] == ["一致", "状态差异待复核", "未完成"]
    report = render_report(date(2026, 10, 7), rows)
    assert "验证不完整" in report.splitlines()[2]
    assert "NUMBER-1" in report
    assert "到达待取（Pick up）" in report


def test_delivered_ahead_of_erp_is_priority_and_info_received_is_reminder():
    rows = [
        {
            "tracking_number": "TRACK-LAG",
            "erp_status_code": "ND",
            "track17_status": "Delivered",
            "track17_checked_at": "2026-10-07 16:00",
        },
        {
            "tracking_number": "TRACK-REMIND",
            "erp_status_code": "ND",
            "track17_status": "Info received",
            "track17_checked_at": "2026-10-07 16:00",
        },
    ]
    results = assess(rows)
    assert [result["verdict"] for result in results] == ["系统落后（重点）", "提醒（系统超前）"]
    assert results[0]["observed_status_name"] == "成功签收"


def test_failed_delivery_after_out_for_delivery_is_priority():
    rows = [
        {
            "tracking_number": "TRACK-FAILED",
            "erp_status_code": "DD",
            "track17_status": "Undelivered",
            "track17_checked_at": "2026-10-08 10:48",
        }
    ]
    assert assess(rows)[0]["verdict"] == "系统落后（重点）"

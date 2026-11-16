"""Read-only contract tests for the weekly-report API client."""

from __future__ import annotations

from typing import Any

import pytest

from modules.auto_test.api.weekly_business_report_api import WeeklyBusinessReportAPI


class FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self.payloads = iter(payloads)
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return FakeResponse(next(self.payloads))


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_customer_bill_api_reads_all_pages_with_the_report_cutoff() -> None:
    session = FakeSession(
        [
            {"code": 200, "rows": [{"id": 1}, {"id": 2}]},
            {"code": 200, "data": {"rows": [{"id": 3}]}},
        ]
    )
    api = WeeklyBusinessReportAPI(session, "https://test.example/api")

    rows = api.list_customer_bills(
        customer_id=123,
        customer_no="DG123",
        end_receivable_date="2026-10-25",
        page_size=2,
    )

    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert [call["method"] for call in session.calls] == ["POST", "POST"]
    assert [call["url"] for call in session.calls] == [
        "https://test.example/api/oms-admin/sales/customerReceivableBill/listOrder",
        "https://test.example/api/oms-admin/sales/customerReceivableBill/listOrder",
    ]
    assert [call["json"]["pageNum"] for call in session.calls] == [1, 2]
    assert all(call["json"]["customerId"] == 123 for call in session.calls)
    assert all(call["json"]["customerNo"] == "DG123" for call in session.calls)
    assert all(call["json"]["endReceivableDate"] == "2026-10-25" for call in session.calls)


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("customer_id", "customer_no", "cutoff", "page_size"),
    [
        (123, "", "2026-10-25", 2),
        (123, "DG123", "", 2),
        (123, "DG123", "2026-10-25", 0),
        (123, "DG123", "2026-10-25", 2001),
    ],
)
def test_customer_bill_api_rejects_invalid_query_bounds(customer_id, customer_no, cutoff, page_size) -> None:
    session = FakeSession([])
    api = WeeklyBusinessReportAPI(session, "https://test.example/api")

    with pytest.raises(ValueError):
        api.list_customer_bills(
            customer_id=customer_id,
            customer_no=customer_no,
            end_receivable_date=cutoff,
            page_size=page_size,
        )

    assert session.calls == []


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_customer_bill_api_stops_after_twenty_full_pages() -> None:
    session = FakeSession([{"code": 200, "rows": [{"id": page}]} for page in range(20)])
    api = WeeklyBusinessReportAPI(session, "https://test.example/api")

    with pytest.raises(AssertionError, match="pagination exceeded 20 pages"):
        api.list_customer_bills(
            customer_id=None,
            customer_no="DG123",
            end_receivable_date="2026-10-25",
            page_size=1,
        )

    assert len(session.calls) == 20


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize("report_id", [0, -1, "abc", "12/other"])
def test_report_detail_api_rejects_invalid_ids_before_sending_a_request(report_id) -> None:
    session = FakeSession([])
    api = WeeklyBusinessReportAPI(session, "https://test.example/api")

    with pytest.raises(ValueError, match="positive integer"):
        api.get_report(report_id)

    assert session.calls == []


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_weekly_report_api_rejects_unsuccessful_envelopes_without_leaking_response_data() -> None:
    session = FakeSession([{"code": 500, "message": "sensitive internal details"}])
    api = WeeklyBusinessReportAPI(session, "https://test.example/api")

    with pytest.raises(AssertionError) as exc_info:
        api.list_reports()

    assert "sensitive internal details" not in str(exc_info.value)

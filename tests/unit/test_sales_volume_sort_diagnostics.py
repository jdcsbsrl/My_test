from types import SimpleNamespace

import pytest

from modules.auto_test.tests.test_sales_volume_sort_regression import (
    REPORT_QUERY_RETRY_DELAYS_MS,
    _assert_report_rows,
    _is_transient_report_server_error,
    _request_diagnostics,
    _report_query_request,
    _response_diagnostics,
    _search_report_rows_with_retry,
)


class FakeResponse:
    def __init__(self, body, *, status=200, content_type="application/json"):
        self.url = "https://test.invalid/oms-admin/sales/report/queryStoreSalesDimensionReport?token=hidden"
        self.status = status
        self.headers = {"content-type": content_type, "content-length": "123"}
        self.request = SimpleNamespace(method="POST")
        self._body = body

    def json(self):
        return self._body


def test_report_query_request_matches_expected_post_endpoint():
    predicate = _report_query_request("queryStoreSalesDimensionReport")
    request = SimpleNamespace(
        url="https://test.invalid/oms-admin/sales/report/queryStoreSalesDimensionReport",
        method="POST",
    )

    assert predicate(request)

    request.method = "GET"
    assert not predicate(request)


def test_response_diagnostics_include_api_error_without_query_string():
    response = FakeResponse({"code": 500, "msg": "服务暂不可用"})

    details = _response_diagnostics(response)

    assert details == {
        "path": "/oms-admin/sales/report/queryStoreSalesDimensionReport",
        "status": 200,
        "contentType": "application/json",
        "contentLength": "123",
        "code": "500",
        "msg": "服务暂不可用",
    }
    assert "token" not in str(details)


def test_request_diagnostics_keep_only_paging_sort_and_date_fields():
    request = SimpleNamespace(
        url="https://test.invalid/oms-admin/sales/report/exportStoreSalesDimensionReport?token=hidden",
        method="POST",
        post_data_json={
            "pageNum": 2,
            "pageSize": 50,
            "sortField": "salesNumber",
            "sortOrder": "desc",
            "payTimeBegin": "2026-10-01 00:00:00",
            "payTimeEnd": "2026-10-31 23:59:59",
            "storeIds": ["private-store-id"],
        },
    )

    details = _request_diagnostics(request)

    assert details["path"] == "/oms-admin/sales/report/exportStoreSalesDimensionReport"
    assert details["pageNum"] == 2
    assert details["pageSize"] == 50
    assert details["sortField"] == "salesNumber"
    assert details["sortOrder"] == "desc"
    assert details["payTimeBegin"] == "2026-10-01 00:00:00"
    assert "private-store-id" not in str(details)
    assert "token" not in str(details)


def test_report_rows_reject_application_error_and_empty_results():
    with pytest.raises(AssertionError, match="服务暂不可用"):
        _assert_report_rows(FakeResponse({"code": 500, "msg": "服务暂不可用"}), "店铺维度", "search")

    with pytest.raises(AssertionError, match="rowCount"):
        _assert_report_rows(FakeResponse({"code": 200, "rows": []}), "店铺维度", "search")


def test_transient_report_5xx_is_retryable_but_auth_errors_are_not():
    assert _is_transient_report_server_error(FakeResponse({"code": 200, "rows": []}, status=503))
    assert _is_transient_report_server_error(FakeResponse({"code": 500, "msg": "restarting"}))
    assert not _is_transient_report_server_error(FakeResponse({"code": 401, "msg": "unauthorized"}))
    assert REPORT_QUERY_RETRY_DELAYS_MS == (5_000, 15_000, 30_000)


def test_sort_search_retries_transient_application_5xx_then_returns_rows():
    class FakeRequest:
        def __init__(self, body):
            self.url = "https://test.invalid/oms-admin/sales/report/queryOmsInventoryNew"
            self.method = "POST"
            self.post_data_json = {"pageNum": 1, "pageSize": 50}
            self.failure = None
            self._response = FakeResponse(body)

        def response(self):
            return self._response

    class FakeExpectation:
        def __init__(self, page):
            self.page = page
            self.value = None

        def __enter__(self):
            self.page.expectation = self
            return self

        def __exit__(self, *_):
            return False

    class FakePage:
        def __init__(self):
            self.requests = [
                FakeRequest({"code": 500, "msg": "restarting"}),
                FakeRequest({"code": 200, "rows": [{"itemId": "SKU-1"}]}),
            ]
            self.expectation = None
            self.waits = []

        def expect_request(self, *_args, **_kwargs):
            return FakeExpectation(self)

        def get_by_role(self, *_args, **_kwargs):
            return self

        def click(self):
            self.expectation.value = self.requests.pop(0)

        def wait_for_timeout(self, delay):
            self.waits.append(delay)

    page = FakePage()
    request, rows = _search_report_rows_with_retry(
        page,
        "queryOmsInventoryNew",
        "SKU\u7ef4\u5ea6",
        set(),
    )

    assert request.post_data_json == {"pageNum": 1, "pageSize": 50}
    assert rows == [{"itemId": "SKU-1"}]
    assert page.waits == [REPORT_QUERY_RETRY_DELAYS_MS[0]]


def test_report_rows_returns_api_rows_after_successful_query():
    rows = [{"itemId": "SKU-1", "salesNumber": 10}]

    assert _assert_report_rows(FakeResponse({"code": 200, "rows": rows}), "SKU维度", "sort") == rows

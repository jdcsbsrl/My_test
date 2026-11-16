from types import SimpleNamespace

import pytest

from modules.auto_test.tests.test_sales_volume_sort_regression import (
    _assert_report_rows,
    _request_diagnostics,
    _report_query_request,
    _response_diagnostics,
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


def test_report_rows_returns_api_rows_after_successful_query():
    rows = [{"itemId": "SKU-1", "salesNumber": 10}]

    assert _assert_report_rows(FakeResponse({"code": 200, "rows": rows}), "SKU维度", "sort") == rows

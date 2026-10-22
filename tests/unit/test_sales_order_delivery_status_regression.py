"""Checks for the read-only delivery-status list regression."""

from contextlib import nullcontext
from urllib.parse import unquote
import json

import modules.auto_test.core.sales_order_delivery_status_regression as regression
from modules.auto_test.__main__ import main as module_main
from modules.auto_test.core.sales_order_delivery_status_regression import (
    STATUS_FLAGS,
    build_payload,
    extract_page,
    inspect_rows,
    query_status,
)


def test_module_command_previews_without_query(capsys):
    assert module_main(["delivery-status-regression", "--env", "uat"]) == 0
    assert "Preview: env=uat" in capsys.readouterr().out


class _Response:
    def __init__(self, rows, total):
        self.rows = rows
        self.total = total

    def raise_for_status(self):
        pass

    def json(self):
        return {"code": 200, "data": {"tableDataInfo": {"rows": self.rows, "total": self.total}}}


class _Client:
    def __init__(self, pages):
        self.pages = pages
        self.payloads = []

    def post(self, path, *, json, timeout):
        self.payloads.append(json)
        page = self.pages[len(self.payloads) - 1]
        if isinstance(page, Exception):
            raise page
        return _Response(*page)


def test_payload_matches_all_four_supplied_filters():
    for _, flag in STATUS_FLAGS:
        payload = build_payload(flag, 1, 500)
        expected = [{"selectType": "47", "selectFlag": flag}]
        assert payload["fixedClassId"] == expected
        assert json.loads(unquote(payload["salesOrderQueryClassDto"])) == expected
        assert payload["orderStatus"] == "0"
        assert payload["queryNotEmptyField"] == "orderId"
        assert payload["pageNum"] == 1
        assert payload["pageSize"] == 500


def test_extract_page_and_inspect_rows():
    rows, total = extract_page(
        {"data": {"tableDataInfo": {"rows": [{"deliveryStatus": 10}, {"deliveryStatus": "30"}, {}], "total": 3}}}
    )
    assert total == 3
    assert inspect_rows(rows, "10") == {
        "row_count": 3,
        "missing_status_count": 1,
        "observed_status_counts": {"10": 1, "30": 1},
        "mismatch_count": 1,
    }
    assert extract_page({"data": {"tableDataInfo": {"rows": None, "total": 0}}}) == ([], 0)


def test_pagination_checks_all_rows():
    client = _Client(
        [
            ([{"orderNo": "SO1", "deliveryStatus": "20"}, {"orderNo": "SO2", "deliveryStatus": "20"}], 3),
            ([{"orderNo": "SO3", "deliveryStatus": "20"}], 3),
        ]
    )
    result = query_status(client, "交运成功", "20", 2, 2)
    assert result["status"] == "PASS"
    assert result["pages_checked"] == 2
    assert result["rows_checked"] == 3
    assert [payload["pageNum"] for payload in client.payloads] == [1, 2]


def test_repeated_order_on_another_page_cannot_pass_as_complete():
    client = _Client(
        [
            ([{"orderNo": "SO1", "deliveryStatus": "20"}, {"orderNo": "SO2", "deliveryStatus": "20"}], 4),
            ([{"orderNo": "SO2", "deliveryStatus": "20"}, {"orderNo": "SO3", "deliveryStatus": "20"}], 4),
        ]
    )
    result = query_status(client, "交运成功", "20", 2, 2)
    assert result["status"] == "PARTIAL"
    assert result["complete"] is False
    assert result["duplicate_order_count"] == 1


def test_multiple_pages_without_order_numbers_cannot_pass_as_complete():
    client = _Client([([{"deliveryStatus": "20"}], 2), ([{"deliveryStatus": "20"}], 2)])
    result = query_status(client, "交运成功", "20", 1, 2)
    assert result["status"] == "PARTIAL"
    assert result["missing_order_no_count"] == 2


def test_repeated_order_id_with_distinct_order_numbers_is_valid():
    client = _Client(
        [
            (
                [
                    {"orderId": 1, "orderNo": "SO1", "deliveryStatus": "20"},
                    {"orderId": 1, "orderNo": "SO2", "deliveryStatus": "20"},
                ],
                2,
            )
        ]
    )
    result = query_status(client, "交运成功", "20", 500, 1)
    assert result["status"] == "PASS"
    assert result["duplicate_order_count"] == 0


def test_empty_transient_result_is_valid_but_has_no_rows_to_verify():
    empty = query_status(_Client([(None, 0)]), "交运中", "10", 500, 1)
    empty_stable = query_status(_Client([(None, 0)]), "交运成功", "20", 500, 1)
    partial = query_status(_Client([([{"deliveryStatus": "0"}], 2)]), "未交运", "0", 1, 1)
    inconsistent_total = query_status(_Client([([{"deliveryStatus": "0"}], 2)]), "未交运", "0", 500, 1)
    assert empty["status"] == "EMPTY_OK"
    assert empty["row_status_verified"] is False
    assert empty_stable["status"] == "NO_SAMPLE"
    assert partial["status"] == "PARTIAL"
    assert inconsistent_total["status"] == "PARTIAL"


def test_transient_status_rows_are_valid_when_all_match():
    result = query_status(_Client([([{"deliveryStatus": "10"}], 1)]), "交运中", "10", 500, 1)
    assert result["status"] == "PASS"
    assert result["row_status_verified"] is True


def test_full_regression_accepts_empty_transient_status(monkeypatch):
    client = _Client(
        [
            ([{"orderNo": "SO0", "deliveryStatus": "0"}], 1),
            (None, 0),
            ([{"orderNo": "SO30", "deliveryStatus": "30"}], 1),
            ([{"orderNo": "SO20", "deliveryStatus": "20"}], 1),
        ]
    )
    monkeypatch.setattr(regression, "regression_session", lambda env: nullcontext(client))
    report = regression.run("test", 500, 1)
    assert report["overall"] == "PASS"
    assert [result["status"] for result in report["results"]] == ["PASS", "EMPTY_OK", "PASS", "PASS"]


def test_mismatch_fails_and_missing_status_blocks():
    mismatch = query_status(_Client([([{"deliveryStatus": "30"}], 1)]), "交运中", "10", 500, 1)
    missing = query_status(_Client([([{}], 1)]), "交运中", "10", 500, 1)
    assert mismatch["status"] == "FAIL"
    assert mismatch["mismatch_count"] == 1
    assert missing["status"] == "BLOCKED"


def test_query_error_preserves_verified_page_counts():
    client = _Client([([{"deliveryStatus": "0"}] * 2, 4), OSError("connection lost")])
    result = query_status(client, "未交运", "0", 2, 2)
    assert result["status"] == "BLOCKED"
    assert result["pages_checked"] == 1
    assert result["rows_checked"] == 2
    assert result["failed_page"] == 2


def test_business_error_is_failure():
    class FailedResponse(_Response):
        def json(self):
            return {"code": 500, "msg": "internal error"}

    client = _Client([])
    client.post = lambda *args, **kwargs: FailedResponse([], 0)
    result = query_status(client, "未交运", "0", 500, 1)
    assert result["status"] == "FAIL"
    assert result["failed_page"] == 1

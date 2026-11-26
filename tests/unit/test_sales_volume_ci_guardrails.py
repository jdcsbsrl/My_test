from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from modules.auto_test.tests.test_sales_volume_regression import (
    OrderSourceScanLimitError,
    _category_order_source_count,
    _category_sku_candidates,
    _fetch_bundle_order_sample,
    _supplier_search_candidate,
    _fetch_order_data,
    _wait_for_sales_volume_report_services,
    test_bundle_order_sample_is_available as _bundle_sample_test,
)


def test_category_candidates_include_only_known_categories_and_are_narrow_first():
    sku_rows = [
        {"itemId": "SKU-A1", "classId": "CAT-A"},
        {"itemId": "SKU-A2", "classId": "CAT-A"},
        {"itemId": "SKU-B1", "classId": "CAT-B"},
        {"itemId": "SKU-UNKNOWN", "classId": "CAT-X"},
    ]
    category_rows = [{"classId": "CAT-A"}, {"classId": "CAT-B"}]

    sku_categories, candidates = _category_sku_candidates(sku_rows, category_rows)

    assert sku_categories == {
        "SKU-A1": "CAT-A",
        "SKU-A2": "CAT-A",
        "SKU-B1": "CAT-B",
    }
    assert candidates == [("CAT-A", ["SKU-A1", "SKU-A2"])]


def test_category_source_count_counts_distinct_active_orders_and_multi_sku_order():
    orders = [
        {"orderNo": "order-1", "orderStatus": "1"},
        {"orderNo": "order-2", "orderStatus": "2"},
        {"orderNo": "order-cancelled", "orderStatus": "6"},
    ]
    details = {
        "order-1": [
            {"itemId": "SKU-A", "quantity": 1},
            {"itemId": "SKU-B", "quantity": 2},
        ],
        "order-2": [{"itemId": "SKU-A", "quantity": 1}],
        "order-cancelled": [
            {"itemId": "SKU-A", "quantity": 1},
            {"itemId": "SKU-B", "quantity": 1},
        ],
    }

    count, has_multi_sku_order, matching_orders = _category_order_source_count(orders, details, {"SKU-A", "SKU-B"})

    assert count == 2
    assert has_multi_sku_order is True
    assert matching_orders == ["order-1", "order-2"]


def test_supplier_sample_uses_most_common_full_name_without_fallback():
    rows = [
        {"itemId": "SKU-A", "defaultSupplier": "清河供应商甲"},
        {"itemId": "SKU-B", "defaultSupplier": "清河供应商乙"},
        {"itemId": "SKU-C", "defaultSupplier": "清河供应商乙"},
        {"itemId": "SKU-D", "defaultSupplier": "阿里供应商"},
    ]

    candidate = _supplier_search_candidate(rows)

    assert candidate == {
        "supplierName": "清河供应商乙",
        "itemIds": ["SKU-B", "SKU-C"],
        "baselineRows": 2,
    }


def test_supplier_filter_searches_and_exports_full_name_from_current_results(monkeypatch):
    from modules.auto_test.tests import test_sales_volume_regression as report_tests

    calls = []
    export_calls = []
    baselines = [{"itemId": "SKU-A", "defaultSupplier": "清河供应商甲"}]

    def report_query(endpoint, payload):
        calls.append(payload)
        supplier_name = payload.get("supplierName")
        if supplier_name == "清河供应商甲":
            return {
                "code": 200,
                "total": 1,
                "rows": [{"itemId": "SKU-B", "defaultSupplier": "清河供应商甲", "salesNumber": 7}],
            }
        if supplier_name:
            return {"code": 200, "total": 0, "rows": []}
        return {"code": 200, "total": len(baselines), "rows": baselines}

    class FakeExportResponse:
        content = b"workbook"

        @staticmethod
        def raise_for_status():
            return None

    class FakeHttpClient:
        def post(self, url, json, timeout):
            export_calls.append((url, json, timeout))
            return FakeExportResponse()

    monkeypatch.setattr(
        report_tests,
        "_read_sku_export",
        lambda _: ({"SKU-B": Decimal("7")}, 1),
    )
    report_tests.test_supplier_name_filter_matches_rows(
        FakeHttpClient(), "https://test.invalid", report_query, ("2026-11-01", "2026-11-30")
    )

    assert [payload.get("supplierName") for payload in calls] == [
        None,
        "清河供应商甲",
        "清河供应商甲",
        "NO-SUCH-SUPPLIER-1003420",
    ]
    assert [url.rsplit("/", 1)[-1] for url, _, _ in export_calls] == [
        "exportOmsInventoryReportV2",
        "exportOmsInventoryReportCurrentPage",
    ]
    assert all(payload.get("supplierName") == "清河供应商甲" for _, payload, _ in export_calls)


def test_supplier_filter_fails_when_a_baseline_supplier_returns_no_rows():
    from modules.auto_test.tests import test_sales_volume_regression as report_tests

    calls = []

    def report_query(endpoint, payload):
        calls.append(payload)
        if payload.get("supplierName"):
            return {"code": 200, "total": 0, "rows": []}
        return {
            "code": 200,
            "total": 1,
            "rows": [{"itemId": "SKU-A", "defaultSupplier": "清河供应商甲"}],
        }

    with pytest.raises(AssertionError):
        report_tests.test_supplier_name_filter_matches_rows(None, None, report_query, ("2026-11-01", "2026-11-30"))

    assert [payload.get("supplierName") for payload in calls] == [None, "清河供应商甲"]


def test_bundle_sample_stops_after_first_page_containing_bundle_details():
    class FakeResponse:
        def __init__(self, body):
            self._body = body

        @staticmethod
        def raise_for_status():
            return None

        def json(self):
            return self._body

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json, timeout):
            self.calls.append((url, json.copy()))
            if url.endswith("batchListNew"):
                return FakeResponse(
                    {
                        "code": 200,
                        "data": {
                            "tableDataInfo": {
                                "rows": [{"orderNo": "order-bundle", "orderStatus": "1"}],
                                "total": 2,
                            }
                        },
                    }
                )
            return FakeResponse(
                {
                    "code": 200,
                    "data": {
                        "order-bundle": [
                            {
                                "itemId": "GROUP-1",
                                "detail": [{"itemId": "SKU-1", "quantity": 1}],
                            }
                        ]
                    },
                }
            )

    session = FakeSession()
    bundles, orders, details = _fetch_bundle_order_sample(
        session,
        "https://test.invalid",
        ("2026-11-01 00:00:00", "2026-11-30 23:59:59"),
        ["store-1"],
        max_pages=20,
        deadline=10**20,
    )

    assert len(bundles) == 1
    assert orders[0]["orderNo"] == "order-bundle"
    assert "order-bundle" in details
    assert len(session.calls) == 2
    assert session.calls[0][1]["pageNum"] == 1


def test_bundle_sample_rejects_partial_order_scan():
    class FakeResponse:
        @staticmethod
        def raise_for_status():
            return None

        def __init__(self, body):
            self._body = body

        def json(self):
            return self._body

    class FakeSession:
        def post(self, url, json, timeout):
            if url.endswith("batchListNew"):
                return FakeResponse(
                    {
                        "code": 200,
                        "data": {"tableDataInfo": {"rows": [{"orderNo": "order-1"}], "total": 2}},
                    }
                )
            return FakeResponse({"code": 200, "data": {"order-1": []}})

    with pytest.raises(OrderSourceScanLimitError, match="exceeded 1 pages"):
        _fetch_bundle_order_sample(
            FakeSession(),
            "https://test.invalid",
            ("2026-11-01 00:00:00", "2026-11-30 23:59:59"),
            [],
            max_pages=1,
            deadline=10**20,
        )


def test_bundle_sample_marks_slow_phase():
    markers = getattr(_bundle_sample_test, "pytestmark", [])

    assert any(getattr(marker, "name", None) == "slow" for marker in markers)


def test_category_order_source_uses_unfiltered_store_orders_for_bundle_items(monkeypatch):
    from modules.auto_test.tests import test_sales_volume_regression as report_tests

    class FakeResponse:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {"code": 200, "data": [{"id": "store-1", "storeName": "Store A"}]}

    class FakeClient:
        @staticmethod
        def post(*args, **kwargs):
            return FakeResponse()

    calls = []
    orders = [
        {"orderNo": "order-bundle", "orderStatus": "1"},
        {"orderNo": "order-single", "orderStatus": "1"},
    ]
    details = {
        "order-bundle": [
            {
                "itemId": "GROUP-B",
                "detail": [
                    {"itemId": "SKU-A", "quantity": 1},
                    {"itemId": "SKU-B", "quantity": 1},
                ],
            }
        ],
        "order-single": [{"itemId": "SKU-A", "quantity": 1}],
    }

    def report_query(endpoint, payload, *, timeout=(10, 180)):
        if endpoint == report_tests.DIMENSIONS["store"]:
            return {"code": 200, "rows": [{"itemId": "SKU-A"}], "total": 1}
        if endpoint == "queryStoreSalesDimensionExpand":
            return {"code": 200, "data": [{"storeName": "Store A"}]}
        if endpoint == report_tests.DIMENSIONS["sku"]:
            return {
                "code": 200,
                "rows": [
                    {"itemId": "SKU-A", "classId": "CAT-1"},
                    {"itemId": "SKU-B", "classId": "CAT-1"},
                ],
                "total": 2,
            }
        if endpoint == report_tests.DIMENSIONS["category"]:
            return {"code": 200, "rows": [{"classId": "CAT-1", "orderNumber": 2}], "total": 1}
        pytest.fail(f"Unexpected report endpoint: {endpoint}")

    def fetch_order_data(*args, **kwargs):
        calls.append((args, kwargs))
        assert "item_ids" not in kwargs
        assert kwargs["max_pages"] == report_tests.CATEGORY_ORDER_SAMPLE_MAX_PAGES
        return orders, details

    monkeypatch.setattr(report_tests, "_fetch_order_data", fetch_order_data)

    report_tests.test_category_distinct_orders_against_order_source(
        FakeClient(),
        "https://test.invalid",
        report_query,
        ("2026-10-15 00:00:00", "2026-11-13 23:59:59"),
    )

    assert len(calls) == 1
    assert calls[0][0][3] == ["store-1"]


def test_readiness_retries_server_error_then_checks_all_procurement_dimensions():
    now = [0.0]

    class FakeResponse:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self._body = body

        def json(self):
            return self._body

    class FakeSession:
        def __init__(self):
            self.calls = []

        def post(self, url, json, timeout):
            self.calls.append((url, json, timeout))
            if len(self.calls) == 1:
                return FakeResponse(503, {"code": 503, "msg": "restarting"})
            return FakeResponse(200, {"code": 200, "rows": [], "total": 0})

    session = FakeSession()

    def sleep(seconds):
        now[0] += seconds

    result = _wait_for_sales_volume_report_services(
        session,
        "https://test.invalid",
        ("2026-10-15 00:00:00", "2026-11-13 23:59:59"),
        "procurement",
        timeout_seconds=10,
        retry_interval=2,
        clock=lambda: now[0],
        sleep=sleep,
    )

    assert result == {
        "attempts": 2,
        "dimensions": ["sku", "warehouse", "country", "category"],
    }
    assert len(session.calls) == 5
    assert all(call[2][1] <= 10 for call in session.calls)


def test_readiness_does_not_retry_authentication_failure():
    class FakeSession:
        calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            return SimpleNamespace(status_code=401, json=lambda: {"code": 401, "msg": "unauthorized"})

    session = FakeSession()

    with pytest.raises(AssertionError, match="authentication failure"):
        _wait_for_sales_volume_report_services(
            session,
            "https://test.invalid",
            ("2026-10-15 00:00:00", "2026-11-13 23:59:59"),
            "procurement",
            timeout_seconds=10,
            clock=lambda: 0,
            sleep=lambda _: None,
        )

    assert session.calls == 1


def test_order_source_scan_fails_incomplete_when_page_limit_is_reached():
    class FakeResponse:
        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {
                "code": 200,
                "data": {
                    "tableDataInfo": {
                        "rows": [{"orderNo": "order-1", "orderStatus": "1"}],
                        "total": 501,
                    }
                },
            }

    class FakeSession:
        calls = 0

        def post(self, *args, **kwargs):
            self.calls += 1
            return FakeResponse()

    session = FakeSession()

    with pytest.raises(OrderSourceScanLimitError, match="exceeded 1 pages"):
        _fetch_order_data(
            session,
            "https://test.invalid",
            ("2026-10-15 00:00:00", "2026-11-13 23:59:59"),
            ["store-1"],
            item_ids=["SKU-A", "SKU-B"],
            max_pages=1,
        )

    assert session.calls == 1

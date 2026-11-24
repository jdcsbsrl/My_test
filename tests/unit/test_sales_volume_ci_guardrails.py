from __future__ import annotations

from types import SimpleNamespace

import pytest

from modules.auto_test.tests.test_sales_volume_regression import (
    OrderSourceScanLimitError,
    _category_order_source_count,
    _category_sku_candidates,
    _fetch_order_data,
    _wait_for_sales_volume_report_services,
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

    count, has_multi_sku_order = _category_order_source_count(orders, details, {"SKU-A", "SKU-B"})

    assert count == 2
    assert has_multi_sku_order is True


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

from datetime import datetime, timedelta

import pytest

from modules.auto_test.tests.test_sales_volume_regression import NoOrderSampleError
from modules.auto_test.tests.test_sales_volume_role_regression import (
    _find_daily_order_sample,
    _find_order_sample_for_reconciliation,
)
from modules.auto_test.core.sales_volume_contract import (
    build_completed_report_window,
    build_report_sample_history_windows,
)

pytestmark = pytest.mark.unit


def test_daily_order_sample_search_skips_empty_days_and_returns_first_complete_day():
    end = "2026-11-23 23:59:59"
    calls = []

    def fetch(window):
        calls.append(window)
        if len(calls) < 3:
            raise NoOrderSampleError("No order sample in this period")
        return [{"orderNo": "sample"}], {"sample": []}

    orders, details, window = _find_daily_order_sample(end, fetch, days=5)

    expected_day = datetime.strptime(end, "%Y-%m-%d %H:%M:%S") - timedelta(days=2)
    assert len(calls) == 3
    assert orders == [{"orderNo": "sample"}]
    assert details == {"sample": []}
    assert window == (
        expected_day.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
        expected_day.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S"),
    )


def test_daily_order_sample_search_does_not_hide_pagination_failures():
    def fetch(_window):
        raise AssertionError("Order pagination incomplete")

    with pytest.raises(AssertionError, match="Order pagination incomplete"):
        _find_daily_order_sample("2026-11-23 23:59:59", fetch, days=5)


def test_daily_order_sample_search_fails_after_the_full_window_is_empty():
    calls = []

    def fetch(window):
        calls.append(window)
        raise NoOrderSampleError("No order sample in this period")

    with pytest.raises(AssertionError, match="INCOMPLETE: no complete daily order sample in the last 4 days"):
        _find_daily_order_sample("2026-11-23 23:59:59", fetch, days=4)
    assert len(calls) == 4


def test_procurement_reconciliation_finds_a_sample_in_bounded_history_windows():
    report_window = build_completed_report_window("2026-11-27")
    history_window = build_report_sample_history_windows(report_window)[0]
    page_calls = []
    day_calls = []

    def fetch_page(window, page_num):
        page_calls.append((window, page_num))
        if window == report_window:
            return {"rows": [], "total": 0}
        return {
            "rows": [
                {
                    "orderNo": "order-1",
                    "orderStatus": "0",
                    "payTime": "2026-10-22 00:54:07",
                }
            ],
            "total": 1,
        }

    def fetch_day(window):
        day_calls.append(window)
        return ([{"orderNo": "order-1"}], {"order-1": [{"itemId": "SKU-A", "quantity": 1}]})

    orders, details, sample_window = _find_order_sample_for_reconciliation(
        report_window,
        fetch_page,
        fetch_day,
    )

    assert page_calls == [(report_window, 1), (history_window, 1)]
    assert day_calls == [("2026-10-22 00:00:00", "2026-10-22 23:59:59")]
    assert orders == [{"orderNo": "order-1"}]
    assert details["order-1"][0]["itemId"] == "SKU-A"
    assert sample_window == day_calls[0]


def test_procurement_reconciliation_reports_incomplete_after_history_is_exhausted():
    report_window = build_completed_report_window("2026-11-27")
    calls = []

    def fetch_page(window, page_num):
        calls.append((window, page_num))
        return {"rows": [], "total": 0}

    with pytest.raises(AssertionError, match="INCOMPLETE: no complete, non-void order sample"):
        _find_order_sample_for_reconciliation(report_window, fetch_page, lambda _window: None)

    assert len(calls) == 7

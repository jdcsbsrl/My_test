from datetime import datetime, timedelta

import pytest

from modules.auto_test.tests.test_sales_volume_regression import NoOrderSampleError
from modules.auto_test.tests.test_sales_volume_role_regression import _find_daily_order_sample

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

    with pytest.raises(AssertionError, match="last 4 days"):
        _find_daily_order_sample("2026-11-23 23:59:59", fetch, days=4)
    assert len(calls) == 4

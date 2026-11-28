"""Boundary tests for the independent requirement-1003838 oracle."""

from datetime import date
from decimal import Decimal

import pytest

from modules.auto_test.core.weekly_business_report_checks import (
    actual_unpaid_amount,
    direct_currency_expectation,
    is_declining_customer,
    is_latest_completed_week_report,
    is_last_week_new_customer,
    is_main_customer,
    is_previous_previous_week_revisit,
    is_weekly_report_unshipped_order,
    latest_completed_week_start,
    amount,
    payment_abnormal_bills,
    should_write_payment_credit_log,
    unshipped_order_ready_percent,
    unshipped_order_ready_percent_from_stock_marks,
)


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("as_of", "expected_start"),
    [
        (date(2026, 11, 23), date(2026, 11, 16)),  # Monday: prior week is complete.
        (date(2026, 11, 24), date(2026, 11, 16)),
        (date(2026, 11, 22), date(2026, 11, 9)),  # Sunday is not complete until day end.
    ],
)
def test_latest_completed_week_start(as_of: date, expected_start: date) -> None:
    assert latest_completed_week_start(as_of) == expected_start


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("report_week_start", "as_of", "expected"),
    [
        ("2026-11-09", date(2026, 11, 23), False),
        ("2026-11-16", date(2026, 11, 23), True),
        ("2026-11-16 00:00:00", date(2026, 11, 24), True),
        (None, date(2026, 11, 23), False),
    ],
)
def test_historical_snapshot_is_not_misidentified_as_latest_complete_week(
    report_week_start: str | None, as_of: date, expected: bool
) -> None:
    assert is_latest_completed_week_report(report_week_start, as_of) is expected


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("recent", "previous", "expected"),
    [
        ("0", "0", False),
        ("1", "0", True),
        ("0", "1", True),
        ("1", "1", True),
    ],
)
def test_main_customer_includes_either_week_with_positive_average(recent, previous, expected) -> None:
    assert is_main_customer(recent, previous) is expected


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("recent", "previous", "expected"),
    [
        ("0", "0", False),
        ("9", "10", False),  # exactly 10% decline
        ("8.5", "10", False),  # exactly 15% decline is excluded
        ("8.49", "10", True),
        ("10", "9", False),
        ("0", "10", True),
    ],
)
def test_decline_requires_more_than_fifteen_percent_and_positive_prior(recent, previous, expected) -> None:
    assert is_declining_customer(recent, previous) is expected


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_payment_abnormal_bill_predicates_keep_null_due_date_and_inclusive_end_date() -> None:
    bills = [
        {"id": 1, "billType": "0", "status": "0", "receivableDate": "2026-10-25", "customerNo": "C1"},
        {"id": 2, "billType": 0, "status": 1, "receivableDate": None, "customerNo": "C1"},
        {"id": 3, "billType": "0", "status": "3", "receivableDate": "2026-10-26", "customerNo": "C1"},
        {"id": 4, "billType": "1", "status": "0", "receivableDate": "2026-10-20", "customerNo": "C1"},
        {"id": 5, "billType": "0", "status": "2", "receivableDate": "2026-10-20", "customerNo": "C1"},
        {"id": 6, "billType": "0", "status": "0", "receivableDate": "2026-10-20", "customerNo": "C2"},
    ]
    selected = payment_abnormal_bills(bills, report_end="2026-10-25", customer_no="C1")
    assert [bill["id"] for bill in selected] == [1, 2]


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize("status", ["0", "1", "3"])
def test_payment_abnormal_bill_predicates_include_each_open_or_unsettled_status(status) -> None:
    bills = [
        {
            "id": status,
            "billType": "0",
            "status": status,
            "receivableDate": "2026-10-25",
            "customerId": 77,
            "customerNo": "C77",
        }
    ]

    selected = payment_abnormal_bills(
        bills,
        report_end="2026-10-25",
        customer_id=77,
        customer_no="C77",
    )

    assert selected == bills


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_all_null_receivable_dates_use_week_end_for_the_display_date() -> None:
    expected = direct_currency_expectation(
        [
            {
                "receivableDate": None,
                "paidButNotReceive": "0",
                "unpaid": "12.34",
                "alreadySendAmount": "0",
                "notSendAmount": "0",
            }
        ],
        report_end="2026-10-25",
    )
    assert expected["pendingPaymentBillDate"] == "2026-10-25"
    assert expected["receivableOutPeriodAmount"] == Decimal("12.34")


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_direct_currency_amounts_reconcile_and_zero_shipping_basis_goes_to_unshipped() -> None:
    expected = direct_currency_expectation(
        [
            {
                "receivableDate": "2026-10-20",
                "paidButNotReceive": "3.00",
                "unpaid": "7.00",
                "alreadySendAmount": "0",
                "notSendAmount": "0",
            },
            {
                "receivableDate": "2026-10-24",
                "paidButNotReceive": "0",
                "unpaid": "10.00",
                "alreadySendAmount": "4.00",
                "notSendAmount": "6.00",
            },
        ],
        report_end="2026-10-25",
    )
    assert expected["paidButNotReceiveAmount"] == Decimal("3.00")
    assert expected["actualUnpaidAmount"] == Decimal("17.00")
    assert expected["receivableAmount"] == Decimal("20.00")
    assert expected["shippedAmount"] == Decimal("4.00")
    assert expected["unshippedAmount"] == Decimal("16.00")
    assert expected["receivableInPeriodAmount"] == Decimal("10.00")
    assert expected["receivableOutPeriodAmount"] == Decimal("10.00")
    assert expected["pendingPaymentBillDate"] == "2026-10-20~2026-10-24"


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_actual_unpaid_deducts_pending_payment_and_never_goes_below_zero() -> None:
    bill = {
        "receivableAmount": "100.00",
        "receivedAmount": "90.00",
        "balanceAmount": "20.00",
        "unpaid": "0.00",
        "paidButNotReceive": "5.00",
        "alreadySendAmount": "33.10",
        "notSendAmount": "33.10",
        "receivableDate": "2026-10-25",
    }
    assert actual_unpaid_amount(bill) == Decimal("0.00")

    expected = direct_currency_expectation([bill], report_end="2026-10-25")
    assert expected["actualUnpaidAmount"] == Decimal("0.00")
    assert expected["receivableAmount"] == Decimal("5.00")
    assert expected["shippedAmount"] == Decimal("2.50")
    assert expected["unshippedAmount"] == Decimal("2.50")
    displayed = direct_currency_expectation([bill], report_end="2026-10-25", use_raw_balances=False)
    assert displayed["receivableAmount"] == Decimal("5.00")


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_shipped_amount_is_clamped_to_report_receivable_and_unshipped_is_remainder() -> None:
    expected = direct_currency_expectation(
        [
            {
                "receivableAmount": "10.00",
                "receivedAmount": "0.00",
                "paidButNotReceive": "10.00",
                "balanceAmount": "0.00",
                "receivableDate": "2026-10-20",
                "alreadySendAmount": "1.00",
                "notSendAmount": "0.00",
            },
            {
                "receivableAmount": "-10.00",
                "receivedAmount": "0.00",
                "paidButNotReceive": "-5.00",
                "balanceAmount": "0.00",
                "receivableDate": "2026-10-21",
                "alreadySendAmount": "0.00",
                "notSendAmount": "1.00",
            },
        ],
        report_end="2026-10-25",
    )
    assert expected["receivableAmount"] == Decimal("5.00")
    assert expected["shippedAmount"] == Decimal("5.00")
    assert expected["unshippedAmount"] == Decimal("0.00")
    assert expected["shippedAmount"] + expected["unshippedAmount"] == expected["receivableAmount"]


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_unpaid_amount_falls_back_to_the_bill_list_value_when_raw_fields_are_incomplete() -> None:
    assert actual_unpaid_amount({"receivableAmount": "100.00", "unpaid": "12.34"}) == Decimal("12.34")


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_shipping_and_term_amounts_conserve_cents_after_ratio_rounding() -> None:
    expected = direct_currency_expectation(
        [
            {
                "receivableDate": "2026-10-20",
                "paidButNotReceive": "0",
                "unpaid": "1.00",
                "alreadySendAmount": "1",
                "notSendAmount": "2",
            },
            {
                "receivableDate": "2026-10-21",
                "paidButNotReceive": "0",
                "unpaid": "0.01",
                "alreadySendAmount": "0",
                "notSendAmount": "0",
            },
        ],
        report_end="2026-10-25",
    )

    assert expected["receivableAmount"] == Decimal("1.01")
    assert expected["shippedAmount"] + expected["unshippedAmount"] == expected["receivableAmount"]
    assert expected["receivableInPeriodAmount"] + expected["receivableOutPeriodAmount"] == expected["receivableAmount"]


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_new_customer_and_old_customer_new_store_rules_are_distinct() -> None:
    week_start, week_end = "2026-10-19", "2026-10-25"
    assert is_last_week_new_customer(cooperation_date="2026-10-19", week_start=week_start, week_end=week_end)
    assert is_last_week_new_customer(
        cooperation_date="2026-01-01",
        week_start=week_start,
        week_end=week_end,
        store_count=2,
        new_store_created_date="2026-10-25",
        new_store_has_any_order=True,
        old_stores_have_any_order=False,
    )
    assert not is_last_week_new_customer(
        cooperation_date="2026-01-01",
        week_start=week_start,
        week_end=week_end,
        store_count=2,
        new_store_created_date="2026-10-25",
        new_store_has_any_order=False,
        old_stores_have_any_order=False,
    )
    assert not is_last_week_new_customer(
        cooperation_date="2026-01-01",
        week_start=week_start,
        week_end=week_end,
        store_count=2,
        new_store_created_date="2026-10-25",
        new_store_has_any_order=True,
        old_stores_have_any_order=True,
    )
    assert not is_last_week_new_customer(
        cooperation_date="2026-01-01",
        week_start=week_start,
        week_end=week_end,
        store_count=1,
        new_store_created_date="2026-10-25",
        new_store_has_any_order=True,
    )


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_revisit_uses_only_cooperation_start_date_in_previous_previous_week() -> None:
    assert is_previous_previous_week_revisit("2026-10-05", period_start="2026-10-05", period_end="2026-10-11")
    assert not is_previous_previous_week_revisit("2026-10-12", period_start="2026-10-05", period_end="2026-10-11")


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("0", True),
        ("1", True),
        ("2", True),
        ("5", True),
        ("7", True),
        ("8", True),
        ("10", True),
        ("6", False),
        ("20", False),
        (None, False),
    ],
)
def test_readiness_ratio_uses_sql_order_status_scope(status, expected) -> None:
    assert is_weekly_report_unshipped_order(status) is expected


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_readiness_ratio_distinguishes_no_unshipped_orders_from_all_shortage() -> None:
    assert unshipped_order_ready_percent([]) is None
    assert unshipped_order_ready_percent([[{"quantity": "2", "lockStockQty": "1"}]]) == Decimal("0.00")
    assert unshipped_order_ready_percent(
        [
            [{"quantity": "2", "lockStockQty": "2"}],
            [{"quantity": "3", "lockStockQty": "1"}],
        ]
    ) == Decimal("50.00")


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_readiness_ratio_uses_order_level_stock_marks() -> None:
    assert unshipped_order_ready_percent_from_stock_marks(["0", "1", "1", "1", "1"]) == Decimal("20.00")
    assert unshipped_order_ready_percent_from_stock_marks([0, 0]) == Decimal("100.00")
    assert unshipped_order_ready_percent_from_stock_marks([1, 1]) == Decimal("0.00")
    assert unshipped_order_ready_percent_from_stock_marks([]) is None
    assert unshipped_order_ready_percent_from_stock_marks(["0", None]) is None


@pytest.mark.unit
@pytest.mark.requirement("1003838")
@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ("优秀", "优秀", False),
        ("一般", "一般", False),
        ("优秀", "一般", True),
        ("一般", "差劲", True),
        (None, None, False),
        (None, "优秀", True),
    ],
)
def test_credit_log_is_only_required_when_the_value_changes(previous, current, expected) -> None:
    assert should_write_payment_credit_log(previous, current) is expected


@pytest.mark.unit
@pytest.mark.requirement("1003838")
def test_amount_parser_accepts_currency_formatted_api_values() -> None:
    assert amount("€ 1,234.50") == Decimal("1234.50")
    assert amount("-94.19") == Decimal("-94.19")

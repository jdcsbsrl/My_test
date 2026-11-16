"""Independent reconciliation helpers for requirement 1003838."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import re
from typing import Any, Iterable

PAYMENT_ABNORMAL_BILL_TYPE = "0"
PAYMENT_ABNORMAL_STATUSES = frozenset({"0", "1", "3"})
CENT = Decimal("0.01")
RAW_UNPAID_FIELDS = ("receivableAmount", "receivedAmount", "balanceAmount")


def amount(value: Any) -> Decimal:
    """Parse an ERP amount without accepting binary floating-point artifacts."""
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Decimal(str(value))
    normalized = str(value).strip().replace(",", "").replace("−", "-")
    match = re.fullmatch(r"[^0-9+\-.]*([+-]?(?:\d+(?:\.\d*)?|\.\d+))[^0-9]*", normalized)
    if not match:
        raise ValueError("ERP amount is not numeric")
    return Decimal(match.group(1))


def _date_part(value: Any) -> str | None:
    if value in (None, ""):
        return None
    result = str(value)[:10]
    date.fromisoformat(result)
    return result


def payment_abnormal_bills(
    bills: Iterable[dict[str, Any]],
    *,
    report_end: str,
    customer_id: int | str | None = None,
    customer_no: str | None = None,
) -> list[dict[str, Any]]:
    """Apply the approved bill type, status, customer and due-date predicates."""
    end_date = _date_part(report_end)
    if end_date is None:
        raise ValueError("report_end is required")
    selected = []
    for bill in bills:
        if str(bill.get("billType")) != PAYMENT_ABNORMAL_BILL_TYPE:
            continue
        if str(bill.get("status")) not in PAYMENT_ABNORMAL_STATUSES:
            continue
        bill_customer_id = bill.get("customerId")
        bill_customer_no = bill.get("customerNo")
        if customer_id is not None and str(bill_customer_id) != str(customer_id):
            continue
        if customer_id is None and customer_no and str(bill_customer_no) != customer_no:
            continue
        due_date = _date_part(bill.get("receivableDate"))
        if due_date is not None and due_date > end_date:
            continue
        selected.append(bill)
    return selected


def actual_unpaid_amount(bill: dict[str, Any]) -> Decimal:
    """Rebuild the weekly-report unpaid formula from raw bill balances.

    The customer-bill list may clamp its display value to zero. When raw
    receivable, received and balance amounts are available, use the report's
    ``receivable - received - balance`` calculation so negative historical
    adjustments are reconciled faithfully.
    """
    if all(field in bill and bill[field] not in (None, "") for field in RAW_UNPAID_FIELDS):
        return amount(bill["receivableAmount"]) - amount(bill["receivedAmount"]) - amount(bill["balanceAmount"])
    return amount(bill.get("unpaid"))


def direct_currency_expectation(
    bills: Iterable[dict[str, Any]], *, report_end: str, use_raw_balances: bool = True
) -> dict[str, Any]:
    """Calculate report amounts from same-currency source bills.

    The shipment split mirrors the approved report rule: distribute
    ``paidButNotReceive + unpaid`` by the source bill's shipped/unshipped
    sales-amount ratio; when both bases are zero, assign the whole amount to
    unshipped. The term split assigns bills on the earliest non-empty due date
    to the in-period amount and the remaining bills to out-of-period.
    """
    source = list(bills)
    if not source:
        raise ValueError("At least one source bill is required")

    dates = [_date_part(bill.get("receivableDate")) for bill in source]
    dated = [value for value in dates if value is not None]
    earliest = min(dated) if dated else None
    latest = max(dated) if dated else None

    paid_pending = Decimal("0")
    actual_unpaid = Decimal("0")
    receivable = Decimal("0")
    shipped = Decimal("0")
    unshipped = Decimal("0")
    in_period = Decimal("0")
    out_period = Decimal("0")

    for bill, due_date in zip(source, dates):
        bill_pending = amount(bill.get("paidButNotReceive"))
        bill_unpaid = actual_unpaid_amount(bill) if use_raw_balances else amount(bill.get("unpaid"))
        bill_receivable = bill_pending + bill_unpaid
        paid_pending += bill_pending
        actual_unpaid += bill_unpaid
        receivable += bill_receivable

        shipped_basis = max(amount(bill.get("alreadySendAmount")), Decimal("0"))
        unshipped_basis = max(amount(bill.get("notSendAmount")), Decimal("0"))
        shipping_basis = shipped_basis + unshipped_basis
        if shipping_basis == 0:
            bill_shipped = Decimal("0")
            bill_unshipped = bill_receivable
        else:
            bill_shipped = (bill_receivable * shipped_basis / shipping_basis).quantize(CENT)
            bill_unshipped = bill_receivable - bill_shipped
        shipped += bill_shipped
        unshipped += bill_unshipped

        if earliest is not None and due_date == earliest:
            in_period += bill_receivable
        else:
            out_period += bill_receivable

    return {
        "paidButNotReceiveAmount": paid_pending,
        "actualUnpaidAmount": actual_unpaid,
        "receivableAmount": receivable,
        "shippedAmount": shipped,
        "unshippedAmount": unshipped,
        "receivableInPeriodAmount": in_period,
        "receivableOutPeriodAmount": out_period,
        "pendingPaymentBillDate": f"{earliest}~{latest}" if dated else str(report_end)[:10],
    }


def is_main_customer(recent_one_week: Any, recent_two_week: Any) -> bool:
    """A main customer has a positive average in either of the two weeks."""
    return amount(recent_one_week) > 0 or amount(recent_two_week) > 0


def is_declining_customer(recent_one_week: Any, recent_two_week: Any) -> bool:
    """Decline is strictly greater than 15%, with a positive prior period."""
    recent = amount(recent_one_week)
    previous = amount(recent_two_week)
    return previous > 0 and recent < previous and (previous - recent) / previous > Decimal("0.15")


def _is_date_in_period(value: Any, *, period_start: str, period_end: str) -> bool:
    normalized = _date_part(value)
    start = _date_part(period_start)
    end = _date_part(period_end)
    if normalized is None or start is None or end is None:
        return False
    if start > end:
        raise ValueError("period_start must not be after period_end")
    return start <= normalized <= end


def is_last_week_new_customer(
    *,
    cooperation_date: Any,
    week_start: str,
    week_end: str,
    store_count: int = 0,
    new_store_created_date: Any = None,
    new_store_has_any_order: bool = False,
    old_stores_have_any_order: bool = False,
) -> bool:
    """Include a newly cooperating customer or an eligible old-customer store.

    ``new_store_has_any_order`` intentionally has no order-date restriction;
    only the store creation date is constrained to the report week.
    """
    if _is_date_in_period(cooperation_date, period_start=week_start, period_end=week_end):
        return True
    return (
        store_count >= 2
        and _is_date_in_period(new_store_created_date, period_start=week_start, period_end=week_end)
        and new_store_has_any_order
        and not old_stores_have_any_order
    )


def is_previous_previous_week_revisit(cooperation_date: Any, *, period_start: str, period_end: str) -> bool:
    """Revisit is based only on the customer cooperation-start date."""
    return _is_date_in_period(cooperation_date, period_start=period_start, period_end=period_end)


def unshipped_order_ready_percent(orders: Iterable[Iterable[dict[str, Any]]]) -> Decimal | None:
    """Return fully-prepared unshipped orders as a percentage; no orders is null."""
    order_lines = [list(lines) for lines in orders]
    if not order_lines:
        return None
    ready_orders = 0
    for lines in order_lines:
        has_shortage = any(amount(line.get("quantity")) > amount(line.get("lockStockQty")) for line in lines)
        if not has_shortage:
            ready_orders += 1
    return (Decimal(ready_orders) * Decimal("100") / Decimal(len(order_lines))).quantize(CENT)


def should_write_payment_credit_log(previous: Any, current: Any) -> bool:
    """The customer credit log changes only when the credit value changes."""
    return previous != current

"""Independent business calculations for inventory sync requirement 1004021."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Iterable

# Confirmed requirement 1004021 status mapping: pending=0, picking=2,
# unpaid=5, WMS shipping=8, and WMS cancel-shipment=10.
UNPAID_STATUS = "5"
ALWAYS_INCLUDED_STATUSES = frozenset({"0", "2", "8", "10"})


@dataclass(frozen=True)
class OrderLine:
    """Normalized order detail used to independently count unshipped quantities."""

    status: str
    is_hold: bool
    deficit_flag: int | None
    sku: str
    quantity: Decimal
    store_name: str = ""


def _decimal(value: Decimal | int | float | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def is_included_unshipped_line(line: OrderLine, *, include_unpaid: bool) -> bool:
    """Return whether one order detail contributes under the selected rule."""
    if line.is_hold:
        return False
    status = str(line.status)
    if status in ALWAYS_INCLUDED_STATUSES:
        return True
    if status != UNPAID_STATUS:
        return False
    if line.deficit_flag not in {0, 1}:
        raise ValueError("待付款订单明细的deficitFlag只能为0或1")
    if include_unpaid:
        return True
    return line.deficit_flag == 0


def aggregate_unshipped_by_sku(lines: Iterable[OrderLine], *, include_unpaid: bool) -> dict[str, Decimal]:
    """Aggregate included order detail quantities by SKU, never by order count."""
    totals: dict[str, Decimal] = {}
    for line in lines:
        if not is_included_unshipped_line(line, include_unpaid=include_unpaid):
            continue
        if not line.sku.strip():
            raise ValueError("included order detail must have a SKU")
        quantity = _decimal(line.quantity)
        if quantity < 0:
            raise ValueError("order detail quantity cannot be negative")
        totals[line.sku] = totals.get(line.sku, Decimal("0")) + quantity
    return totals


def combination_capacity(
    child_quantities: dict[str, Decimal | int | str], recipe: dict[str, Decimal | int | str]
) -> int:
    """Calculate whole combination sets from child inventory and per-set usage."""
    if not recipe:
        raise ValueError("combination recipe cannot be empty")
    capacities: list[int] = []
    for sku, usage_value in recipe.items():
        usage = _decimal(usage_value)
        if usage <= 0:
            raise ValueError(f"child SKU usage must be positive: {sku}")
        available = _decimal(child_quantities.get(sku, 0))
        if available < 0:
            raise ValueError(f"child SKU quantity cannot be negative: {sku}")
        capacities.append(int((available / usage).to_integral_value(rounding=ROUND_FLOOR)))
    return min(capacities)


def calculate_sync_formula(
    *,
    stock: Decimal | int | float | str,
    in_transit: Decimal | int | float | str,
    unshipped: Decimal | int | float | str,
    stock_percent: Decimal | int | float | str = 100,
    transit_percent: Decimal | int | float | str = 100,
    unshipped_percent: Decimal | int | float | str = 100,
    result_percent: Decimal | int | float | str = 100,
) -> Decimal:
    """Calculate the unrounded formula result; callers must use ERP rounding policy."""
    weighted = (
        _decimal(stock) * _decimal(stock_percent)
        + _decimal(in_transit) * _decimal(transit_percent)
        - _decimal(unshipped) * _decimal(unshipped_percent)
    ) / Decimal("100")
    return weighted * _decimal(result_percent) / Decimal("100")


def final_sync_quantity(formula_result: Decimal | int | float | str) -> Decimal:
    """Clamp negative stock to zero while preserving fractional precision."""
    return max(Decimal("0"), _decimal(formula_result))

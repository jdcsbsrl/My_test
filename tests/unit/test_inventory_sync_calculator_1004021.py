from __future__ import annotations

from decimal import Decimal

import pytest

from modules.auto_test.core.inventory_sync_calculator import (
    OrderLine,
    aggregate_unshipped_by_sku,
    calculate_sync_formula,
    combination_capacity,
    final_sync_quantity,
    is_included_unshipped_line,
)


@pytest.mark.unit
@pytest.mark.parametrize("status", ["0", "2", "8", "10"])
def test_active_unshipped_statuses_count_in_both_modes(status: str) -> None:
    line = OrderLine(status, False, None, "STOCK-SKU", Decimal("3"))

    assert is_included_unshipped_line(line, include_unpaid=False)
    assert is_included_unshipped_line(line, include_unpaid=True)


@pytest.mark.unit
@pytest.mark.parametrize("deficit_flag", [0, 1])
def test_unpaid_deficit_flag_is_interpreted_by_selected_mode(deficit_flag: int) -> None:
    line = OrderLine("5", False, deficit_flag, "STOCK-SKU", Decimal("2"))

    assert is_included_unshipped_line(line, include_unpaid=True)
    assert is_included_unshipped_line(line, include_unpaid=False) is (deficit_flag == 0)


@pytest.mark.unit
@pytest.mark.parametrize("status,deficit_flag", [("0", None), ("2", None), ("5", 0), ("5", 1)])
def test_hold_orders_are_excluded_for_every_supported_state(status: str, deficit_flag: int | None) -> None:
    line = OrderLine(status, True, deficit_flag, "STOCK-SKU", Decimal("7"))

    assert not is_included_unshipped_line(line, include_unpaid=False)
    assert not is_included_unshipped_line(line, include_unpaid=True)


@pytest.mark.unit
def test_non_supported_status_is_excluded_and_unknown_unpaid_flag_fails() -> None:
    unsupported = OrderLine("6", False, None, "STOCK-SKU", Decimal("5"))
    unknown_flag = OrderLine("5", False, None, "STOCK-SKU", Decimal("5"))

    assert not is_included_unshipped_line(unsupported, include_unpaid=True)
    with pytest.raises(ValueError, match="deficitFlag只能为0或1"):
        is_included_unshipped_line(unknown_flag, include_unpaid=True)
    with pytest.raises(ValueError, match="deficitFlag只能为0或1"):
        is_included_unshipped_line(unknown_flag, include_unpaid=False)


@pytest.mark.unit
def test_aggregation_counts_sku_units_across_orders_not_order_rows() -> None:
    lines = [
        OrderLine("0", False, None, "STOCK-SKU", Decimal("2")),
        OrderLine("2", False, None, "STOCK-SKU", Decimal("3")),
        OrderLine("5", False, 1, "STOCK-SKU", Decimal("4")),
    ]

    assert aggregate_unshipped_by_sku(lines, include_unpaid=False) == {"STOCK-SKU": Decimal("5")}
    assert aggregate_unshipped_by_sku(lines, include_unpaid=True) == {"STOCK-SKU": Decimal("9")}


@pytest.mark.unit
def test_combination_capacity_uses_bottleneck_child_recipe() -> None:
    capacity = combination_capacity(
        {"CHILD-A": 9, "CHILD-B": 7, "CHILD-C": 12},
        {"CHILD-A": 1, "CHILD-B": 1, "CHILD-C": 2},
    )

    assert capacity == 6


@pytest.mark.unit
def test_inventory_sku_two_unpaid_modes_have_expected_formula_delta() -> None:
    without_unpaid = calculate_sync_formula(stock=30, in_transit=4, unshipped=29)
    with_unpaid = calculate_sync_formula(stock=30, in_transit=4, unshipped=31)

    assert final_sync_quantity(without_unpaid) == Decimal("5")
    assert final_sync_quantity(with_unpaid) == Decimal("3")
    assert without_unpaid - with_unpaid == Decimal("2")


@pytest.mark.unit
def test_combination_sku_two_unpaid_modes_have_expected_formula_delta() -> None:
    without_unpaid = calculate_sync_formula(stock=-9, in_transit=123, unshipped=0)
    with_unpaid = calculate_sync_formula(stock=-11, in_transit=123, unshipped=0)

    assert final_sync_quantity(without_unpaid) == Decimal("114")
    assert final_sync_quantity(with_unpaid) == Decimal("112")
    assert without_unpaid - with_unpaid == Decimal("2")


@pytest.mark.unit
def test_formula_applies_each_percent_independently_and_preserves_decimal() -> None:
    result = calculate_sync_formula(
        stock=10,
        in_transit=8,
        unshipped=3,
        stock_percent=50,
        transit_percent=25,
        unshipped_percent=60,
        result_percent=50,
    )

    assert result == Decimal("2.6")


@pytest.mark.unit
def test_negative_formula_result_is_clamped_to_zero() -> None:
    result = calculate_sync_formula(stock=1, in_transit=0, unshipped=2)

    assert result == Decimal("-1")
    assert final_sync_quantity(result) == Decimal("0")


@pytest.mark.unit
def test_combination_recipe_rejects_non_positive_child_usage() -> None:
    with pytest.raises(ValueError, match="usage must be positive"):
        combination_capacity({"CHILD-A": 10}, {"CHILD-A": 0})

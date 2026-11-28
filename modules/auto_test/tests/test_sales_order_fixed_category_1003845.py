"""UI regression for sales-order fixed-category requirement 1003845."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from modules.auto_test.core.sales_order_quantity_filter import metrics_by_order
from modules.auto_test.pages.sales_order_fixed_category_page import SalesOrderFixedCategoryPage

GREATER_VALUES = [1, 2, 3, 4, 5, 6, 10, 15, 20, 30]
EQUAL_VALUES = list(range(1, 11))


def _page(logged_in_page: Page, config_manager) -> SalesOrderFixedCategoryPage:
    fixed = SalesOrderFixedCategoryPage(logged_in_page, config_manager.base_url)
    fixed.open()
    return fixed


def _assert_response_data(order_response, item_response) -> dict:
    order_payload = order_response.json()
    assert order_payload.get("code") == 200, order_payload
    rows = order_payload.get("data", {}).get("tableDataInfo", {}).get("rows", [])
    assert rows, "筛选结果为空，无法验证订单产品数量"
    expected_orders = {str(row["orderNo"]) for row in rows}
    metrics = metrics_by_order(item_response.json())
    assert metrics, "订单明细接口未返回可核对数据"
    missing = expected_orders - set(metrics)
    assert not missing, f"明细接口缺少列表订单: {sorted(missing)[:5]}"
    return {order: metrics[order] for order in expected_orders}


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p0
@pytest.mark.requirement("1003845")
def test_fixed_category_names_and_options(logged_in_page: Page, config_manager) -> None:
    fixed = _page(logged_in_page, config_manager)
    dropdown_text = fixed.visible_dropdown_text()
    failures: list[str] = []
    if "多产品种类" not in dropdown_text:
        failures.append("缺少名称“多产品种类”")
    if "多产品种类数量" not in dropdown_text:
        failures.append("缺少名称“多产品种类数量”")
    if "多产品指定数量" in dropdown_text:
        failures.append("旧名称“多产品指定数量”仍在显示")
    multi_kind_values = fixed.option_values("多产品种类")
    expected_multi_kind_values = [
        "1个以上",
        "2个以上",
        "3个以上",
        "4个以上",
        "5个以上",
        "6个以上",
        "10个以上",
        "15个以上",
        "20个以上",
        "30个以上",
    ]
    if multi_kind_values != expected_multi_kind_values:
        failures.append(f"多产品种类选项错误: {multi_kind_values}")
    fixed.open_fixed_category()
    single_values = fixed.option_values("单产品单数量")
    if single_values != ["正选", "反选"]:
        failures.append(f"单产品单数量选项应为正选/反选，实际: {single_values}")
    fixed.open_fixed_category()
    greater_values = fixed.option_values("产品个数大于")
    if greater_values != [f"{value}个" for value in GREATER_VALUES]:
        failures.append(f"产品个数大于选项错误: {greater_values}")
    fixed.open_fixed_category()
    equal_values = fixed.option_values("产品个数等于")
    if equal_values != [f"{value}个" for value in EQUAL_VALUES]:
        failures.append(f"产品个数等于选项错误: {equal_values}")
    assert not failures, "\n".join(failures)


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p0
@pytest.mark.requirement("1003845")
def test_product_count_equal_all_values(logged_in_page: Page, config_manager) -> None:
    fixed = _page(logged_in_page, config_manager)
    failures: list[str] = []
    for value in EQUAL_VALUES:
        try:
            fixed.select_filter("产品个数等于", f"{value}个")
            order_response, item_response = fixed.search_responses("52", str(value))
            assert fixed.fixed_condition(order_response) == {
                "selectType": "52",
                "selectFlag": str(value),
            }
            metrics = _assert_response_data(order_response, item_response)
            mismatches = {order: metric for order, metric in metrics.items() if metric.total_quantity != value}
            assert not mismatches, f"返回数量不等的订单: {list(mismatches.items())[:10]}"
        except AssertionError as exc:
            failures.append(f"产品个数等于{value}: {exc}")
    assert not failures, "\n".join(failures)


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p0
@pytest.mark.requirement("1003845")
def test_product_count_greater_all_values(logged_in_page: Page, config_manager) -> None:
    fixed = _page(logged_in_page, config_manager)
    failures: list[str] = []
    for value in GREATER_VALUES:
        try:
            fixed.select_filter("产品个数大于", f"{value}个")
            order_response, item_response = fixed.search_responses("51", str(value))
            assert fixed.fixed_condition(order_response) == {
                "selectType": "51",
                "selectFlag": str(value),
            }
            metrics = _assert_response_data(order_response, item_response)
            mismatches = {order: metric for order, metric in metrics.items() if metric.total_quantity <= value}
            assert not mismatches, f"返回未越过边界的订单: {list(mismatches.items())[:10]}"
        except AssertionError as exc:
            failures.append(f"产品个数大于{value}: {exc}")
    assert not failures, "\n".join(failures)


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p0
@pytest.mark.requirement("1003845")
def test_single_product_single_quantity_semantics(logged_in_page: Page, config_manager) -> None:
    fixed = _page(logged_in_page, config_manager)
    failures: list[str] = []
    submitted_flags: list[str] = []
    submitted_types: list[str] = []
    for option, flag, positive in (("正选", "1", True), ("反选", "0", False)):
        fixed.select_filter("单产品单数量", option)
        order_response, item_response = fixed.search_responses("50", flag)
        condition = fixed.fixed_condition(order_response)
        submitted_types.append(condition["selectType"])
        submitted_flags.append(condition["selectFlag"])
        metrics = _assert_response_data(order_response, item_response)
        if positive:
            mismatches = {
                order: metric
                for order, metric in metrics.items()
                if metric.sku_types != 1 or metric.total_quantity != 1
            }
        else:
            mismatches = {
                order: metric
                for order, metric in metrics.items()
                if metric.sku_types == 1 and metric.total_quantity == 1
            }
        if mismatches:
            failures.append(f"单产品单数量{option}语义错误: {list(mismatches.items())[:10]}")
    assert len(set(submitted_flags)) == 2, f"单数量与多数量提交了相同参数: {submitted_flags}"
    assert len(set(submitted_types)) == 1, f"单数量与多数量提交了不同分类: {submitted_types}"
    assert not failures, "\n".join(failures)

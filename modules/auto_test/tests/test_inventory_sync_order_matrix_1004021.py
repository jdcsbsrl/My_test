"""Read-only live order-source preflight for requirement 1004021."""

from __future__ import annotations

import os
from decimal import Decimal

import allure
import pytest

from modules.auto_test.api.inventory_sync_order_api import InventorySyncOrderAPI
from modules.auto_test.core.inventory_sync_calculator import aggregate_unshipped_by_sku

REQUIRED_STATUSES = {"0", "2", "5", "8", "10"}
TARGET_SKUS = {"DWOYX-LF006", "Merge001"}
TARGET_STORE = "yxl_kehu_zuzhang-test_yxl_new"


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
@pytest.mark.slow
@pytest.mark.requirement(id="1004021")
@allure.feature("ERP库存同步")
@allure.story("需求1004021订单数据矩阵")
def test_seed_order_matrix_covers_status_hold_and_deficit_modes(authenticated_http_client, api_base_url: str) -> None:
    """Fail closed unless the configured order set covers every required branch."""
    order_numbers = [
        value.strip() for value in os.getenv("INVENTORY_SYNC_ORDER_NUMBERS", "").split(",") if value.strip()
    ]
    assert order_numbers, "缺少INVENTORY_SYNC_ORDER_NUMBERS，未配置需求1004021的TEST预置订单"

    api = InventorySyncOrderAPI(authenticated_http_client, api_base_url)
    lines = api.fetch_order_lines(order_numbers)
    assert lines, "预置订单没有可用于库存同步的明细"
    stores = {line.store_name for line in lines}
    assert stores == {TARGET_STORE}, f"订单必须全部属于规则店铺 {TARGET_STORE}: {sorted(stores)}"

    statuses = {line.status for line in lines}
    missing_statuses = sorted(REQUIRED_STATUSES - statuses)

    unpaid = [line for line in lines if line.status == "5" and not line.is_hold]
    assert all(line.deficit_flag in {0, 1} for line in unpaid), "待付款样本的deficitFlag只能为0或1"
    assert {line.deficit_flag for line in unpaid} >= {0, 1}, "待付款样本必须同时包含deficitFlag=0和1"
    for deficit_flag in (0, 1):
        flagged_skus = {line.sku for line in unpaid if line.deficit_flag == deficit_flag}
        assert TARGET_SKUS <= flagged_skus, f"待付款 deficitFlag={deficit_flag} 样本未同时覆盖两个目标SKU"
    for status in REQUIRED_STATUSES - set(missing_statuses):
        status_skus = {line.sku for line in lines if line.status == status}
        assert TARGET_SKUS <= status_skus, f"状态码 {status} 样本未同时覆盖两个目标SKU"
    held_skus = {line.sku for line in lines if line.status in {"0", "2", "5"} and line.is_hold}
    assert TARGET_SKUS <= held_skus, "Hold排除样本未同时覆盖两个目标SKU"

    without_unpaid = aggregate_unshipped_by_sku(lines, include_unpaid=False)
    with_unpaid = aggregate_unshipped_by_sku(lines, include_unpaid=True)
    expected_delta: dict[str, Decimal] = {}
    for line in unpaid:
        if line.deficit_flag == 1 and line.sku in TARGET_SKUS:
            expected_delta[line.sku] = expected_delta.get(line.sku, Decimal("0")) + line.quantity

    for sku in TARGET_SKUS:
        actual_delta = with_unpaid.get(sku, Decimal("0")) - without_unpaid.get(sku, Decimal("0"))
        assert actual_delta == expected_delta.get(sku, Decimal("0")), (
            f"SKU {sku} 两个待付款口径差值不等于deficitFlag=1的非Hold订单量: "
            f"actual={actual_delta}, expected={expected_delta.get(sku, Decimal('0'))}"
        )

    allure.attach(
        f"orders={len(set(order_numbers))}; statuses={sorted(statuses)}; missing_statuses={missing_statuses}; "
        f"without_unpaid={without_unpaid}; with_unpaid={with_unpaid}",
        name="需求1004021订单统计预检",
        attachment_type=allure.attachment_type.TEXT,
    )
    assert not missing_statuses, (
        f"订单样本覆盖不完整，缺少状态码: {missing_statuses}; "
        f"without_unpaid={without_unpaid}; with_unpaid={with_unpaid}"
    )

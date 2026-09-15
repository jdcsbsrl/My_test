"""Regression tests for ERP inventory SKUs and combination SKU definitions."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import allure
import pytest

from modules.auto_test.api.inventory_sku_api import InventorySKUAPI
from modules.auto_test.api.inventory_variant_stock_api import InventoryVariantStockAPI
from modules.auto_test.api.sku_group_api import SKUGroupAPI

DATA_FILE = Path(__file__).resolve().parents[3] / "fixtures" / "inventory_variant_stock_test_data.json"
INVENTORY_FIELDS = (
    "stockQty",
    "availableInventory",
    "inTransitQty",
    "unShippedQty",
    "unTransitQty",
    "saleSeven",
    "saleFifteen",
    "saleThirty",
)
COMBINATION_ITEM_IDS = ("Merge001", "Merge002", "Merge003")
STOCK_STATES = {"0", "1", "2", "3", "4"}
ONLINE_VALIDATION_FIELDS = (
    "stockSku",
    "erpTitle",
    "englishName",
    "imgUrl",
    "locationId",
    "warehouse",
)
ONLINE_TO_INVENTORY_FIELDS = {
    "erpTitle": "displayName",
    "englishName": "englishName",
    "imgUrl": "imgUrl",
}


def _fixture_data() -> dict[str, Any]:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _normal_variant_cases() -> tuple[tuple[str, str], ...]:
    return tuple(
        (variant["variantId"], variant["itemId"])
        for variant in _fixture_data()["variants"]
        if not str(variant["itemId"]).startswith("Merge")
    )


def _normal_item_ids() -> tuple[str, ...]:
    return tuple(dict.fromkeys(item_id for _, item_id in _normal_variant_cases()))


@pytest.fixture(scope="function")
def inventory_sku_api(authenticated_http_client, api_base_url: str) -> InventorySKUAPI:
    return InventorySKUAPI(authenticated_http_client, api_base_url)


@pytest.fixture(scope="function")
def variant_stock_api(authenticated_http_client, api_base_url: str) -> InventoryVariantStockAPI:
    return InventoryVariantStockAPI(authenticated_http_client, api_base_url)


@pytest.fixture(scope="function")
def sku_group_api(authenticated_http_client, api_base_url: str) -> SKUGroupAPI:
    return SKUGroupAPI(authenticated_http_client, api_base_url)


def _inventory_payload(item_id: str) -> dict[str, Any]:
    return {
        "beginCreateTime": "",
        "endCreateTime": "",
        "itemId": item_id,
        "pageNum": 1,
        "pageSize": 20,
        "salesStatusList": ["0"],
        "searchMode": "3",
    }


def _decimal(row: dict[str, Any], field: str) -> Decimal | None:
    value = row.get(field)
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _expected_stock_state(row: dict[str, Any]) -> str | None:
    """Translate the supplied UI rules into a testable state when boundaries are clear."""
    stock_qty = _decimal(row, "stockQty")
    in_transit = _decimal(row, "inTransitQty")
    # The online-stock endpoint exposes the corresponding pending quantity as
    # ``pendingFulfillment``; in listNew data it aligns with ``unTransitQty``.
    unshipped = _decimal(row, "unTransitQty")
    sale_seven = _decimal(row, "saleSeven")
    sale_fifteen = _decimal(row, "saleFifteen")
    sale_thirty = _decimal(row, "saleThirty")
    values = (stock_qty, in_transit, unshipped, sale_seven, sale_fifteen, sale_thirty)
    if any(value is None for value in values):
        return None

    assert stock_qty is not None
    assert in_transit is not None
    assert unshipped is not None
    assert sale_seven is not None
    assert sale_fifteen is not None
    assert sale_thirty is not None

    current_minus_unshipped = stock_qty - unshipped
    projected = stock_qty + in_transit - unshipped

    if current_minus_unshipped <= 0:
        return "0"
    if stock_qty > 0 and sale_fifteen == 0:
        return "1"
    if projected < sale_seven:
        return "2"
    if sale_seven < projected < sale_thirty:
        return "3"
    if projected > sale_thirty:
        return "4"
    return None


def _is_empty(value: Any) -> bool:
    return value is None or value == ""


def _same_optional_value(left: Any, right: Any) -> bool:
    """Treat null and empty string as the same empty API value."""
    if _is_empty(left) and _is_empty(right):
        return True
    return left == right


def _all_online_stock_rows(
    variant_stock_api: InventoryVariantStockAPI,
    data: dict[str, Any],
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Read every online-stock page and guard against pagination omissions."""
    params = {
        "storeId": str(data["storeId"]),
        "customerId": str(data["customerId"]),
        "productId": str(data["productId"]),
        "pageSize": str(page_size),
        "pageNum": "1",
    }
    first_body = variant_stock_api.query_page(params)
    first_envelope = variant_stock_api.assert_success(first_body)
    total = first_envelope["total"]
    rows = list(variant_stock_api.rows(first_body))
    page_count = max(1, (total + page_size - 1) // page_size)

    for page_num in range(2, page_count + 1):
        page_body = variant_stock_api.query_page({**params, "pageNum": str(page_num)})
        variant_stock_api.assert_success(page_body)
        rows.extend(variant_stock_api.rows(page_body))

    assert len(rows) == total, f"在线库存分页结果不完整: total={total}, actual={len(rows)}"
    fingerprints = [
        (
            row.get("productId"),
            row.get("variantId"),
            row.get("platformSku"),
            row.get("stockSku"),
            row.get("skuColorSize"),
        )
        for row in rows
    ]
    assert len(fingerprints) == len(set(fingerprints)), "在线库存分页存在重复记录"
    return rows


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
@pytest.mark.parametrize("item_id", _normal_item_ids())
def test_inventory_list_returns_each_normal_bound_item(
    inventory_sku_api,
    item_id: str,
) -> None:
    """普通 ERP 库存 SKU 可以按 itemId 精确查询。"""
    body = inventory_sku_api.list_page(_inventory_payload(item_id))
    table = inventory_sku_api.assert_success(body)
    rows = inventory_sku_api.rows(body)

    assert table["total"] >= 1, f"itemId={item_id} 未查到库存 SKU"
    assert rows
    assert all(str(row.get("itemId")) == item_id for row in rows)
    assert all(str(row.get("salesStatus")) == "0" for row in rows)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
def test_inventory_list_exposes_stock_state_calculation_inputs(inventory_sku_api) -> None:
    """库存接口返回状态计算需要的库存、在途、未发货和销量字段。"""
    body = inventory_sku_api.list_page(_inventory_payload("DWOYX-LI001"))
    inventory_sku_api.assert_success(body)
    rows = inventory_sku_api.rows(body)
    assert rows

    for row in rows:
        for field in INVENTORY_FIELDS:
            assert field in row, f"库存 SKU 响应缺少状态计算字段 {field}: {row}"
            assert _decimal(row, field) is not None, f"状态计算字段 {field} 不应为空: {row}"


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
@pytest.mark.parametrize("variant_id,item_id", _normal_variant_cases())
def test_variant_stock_state_matches_inventory_calculation(
    inventory_sku_api,
    variant_stock_api,
    variant_id: str,
    item_id: str,
) -> None:
    """普通 SKU 的库存状态应符合截图中的状态计算规则。"""
    inventory_body = inventory_sku_api.list_page(_inventory_payload(item_id))
    inventory_sku_api.assert_success(inventory_body)
    inventory_rows = inventory_sku_api.rows(inventory_body)
    assert inventory_rows, f"itemId={item_id} 未返回库存计算数据"

    expected_state = _expected_stock_state(inventory_rows[0])
    if expected_state is None:
        pytest.skip(f"itemId={item_id} 命中状态边界或缺少可用于判定的销量字段")

    variant_body = variant_stock_api.query_page(
        {
            "storeId": str(_fixture_data()["storeId"]),
            "customerId": str(_fixture_data()["customerId"]),
            "variantId": variant_id,
        }
    )
    variant_stock_api.assert_success(variant_body)
    variant_rows = variant_stock_api.rows(variant_body)
    assert variant_rows
    assert all(str(row.get("variantId")) == variant_id for row in variant_rows)
    actual_states = sorted({str(row.get("stockState")) for row in variant_rows})
    inventory_evidence = {field: inventory_rows[0].get(field) for field in INVENTORY_FIELDS}
    variant_evidence = [
        {
            field: row.get(field)
            for field in (
                "variantId",
                "stockSku",
                "availableStock",
                "inboundStock",
                "pendingFulfillment",
                "stockState",
            )
        }
        for row in variant_rows
    ]
    assert actual_states == [expected_state], (
        f"itemId={item_id}, variantId={variant_id} 状态不一致: "
        f"expected={expected_state}, actual={actual_states}, inventory={inventory_evidence}, "
        f"variant={variant_evidence}"
    )


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
def test_linked_stock_skus_match_inventory_master_fields(
    inventory_sku_api,
    variant_stock_api,
    sku_group_api,
) -> None:
    """库存 SKU 不为空时，应能回查并映射库存主数据字段。"""
    data = _fixture_data()
    online_rows = _all_online_stock_rows(variant_stock_api, data)
    linked_rows = [row for row in online_rows if not _is_empty(row.get("stockSku"))]
    assert linked_rows, "在线库存数据没有返回可用于回查的 stockSku"

    inventory_cache: dict[str, dict[str, Any]] = {}
    combination_cache: dict[str, dict[str, Any]] = {}
    field_stats = {
        field: {"source_present": 0, "online_present": 0, "matched": 0} for field in ONLINE_TO_INVENTORY_FIELDS
    }
    stock_state_counts: dict[str, int] = {}

    for online_row in linked_rows:
        stock_sku = str(online_row["stockSku"])
        actual_state = str(online_row.get("stockState"))
        assert actual_state in STOCK_STATES, f"stockSku={stock_sku} 返回非法 stockState={actual_state!r}"
        stock_state_counts[actual_state] = stock_state_counts.get(actual_state, 0) + 1
        if stock_sku in COMBINATION_ITEM_IDS:
            if stock_sku not in combination_cache:
                group_body = sku_group_api.list_page(stock_sku)
                sku_group_api.assert_success(group_body)
                group_rows = sku_group_api.rows(group_body)
                matching_groups = [row for row in group_rows if str(row.get("groupSkuId")) == stock_sku]
                assert matching_groups, f"组合 stockSku={stock_sku} 无法通过组合 SKU接口回查"
                assert len(matching_groups) == 1, f"组合 stockSku={stock_sku} 返回多条主记录: {matching_groups}"
                combination_cache[stock_sku] = matching_groups[0]
            # Combination SKUs are validated by skuGroup/list; they do not
            # have a normal inventory/listNew master row to map these fields.
            assert str(combination_cache[stock_sku].get("groupSkuId")) == stock_sku
            assert _is_empty(online_row.get("locationId")), f"组合 stockSku={stock_sku} 的 locationId 当前应为空"
            assert _is_empty(online_row.get("warehouse")), f"组合 stockSku={stock_sku} 的 warehouse 当前应为空"
            continue

        if stock_sku not in inventory_cache:
            inventory_body = inventory_sku_api.list_page(_inventory_payload(stock_sku))
            inventory_sku_api.assert_success(inventory_body)
            inventory_rows = inventory_sku_api.rows(inventory_body)
            matching_rows = [row for row in inventory_rows if str(row.get("itemId")) == stock_sku]
            assert matching_rows, f"stockSku={stock_sku} 无法通过库存 SKU 接口回查 itemId"
            assert len(matching_rows) == 1, f"stockSku={stock_sku} 通过库存 SKU接口返回多条匹配记录: {matching_rows}"
            inventory_cache[stock_sku] = matching_rows[0]

        inventory_row = inventory_cache[stock_sku]
        assert str(inventory_row.get("itemId")) == stock_sku
        expected_state = _expected_stock_state(inventory_row)
        assert expected_state is not None, f"stockSku={stock_sku} 缺少可计算 stockState 的库存字段: {inventory_row}"
        assert actual_state == expected_state, (
            f"stockSku={stock_sku} 的 stockState 计算不一致: "
            f"expected={expected_state}, actual={actual_state}, inventory={inventory_row}"
        )

        for online_field, inventory_field in ONLINE_TO_INVENTORY_FIELDS.items():
            online_value = online_row.get(online_field)
            inventory_value = inventory_row.get(inventory_field)
            if not _is_empty(inventory_value):
                field_stats[online_field]["source_present"] += 1
            if not _is_empty(online_value):
                field_stats[online_field]["online_present"] += 1
            assert _same_optional_value(online_value, inventory_value), (
                f"stockSku={stock_sku} 字段映射不一致: "
                f"online.{online_field}={online_value!r}, "
                f"inventory.{inventory_field}={inventory_value!r}"
            )
            field_stats[online_field]["matched"] += 1

        # The current API contract reserves these fields; the endpoint should
        # keep them empty until warehouse/location aggregation is released.
        assert _is_empty(
            online_row.get("locationId")
        ), f"stockSku={stock_sku} 的 locationId 当前应为空，实际为 {online_row.get('locationId')!r}"
        assert _is_empty(
            online_row.get("warehouse")
        ), f"stockSku={stock_sku} 的 warehouse 当前应为空，实际为 {online_row.get('warehouse')!r}"

    allure.attach(
        json.dumps(
            {
                "online_total": len(online_rows),
                "online_missing_counts": {
                    field: sum(_is_empty(row.get(field)) for row in online_rows) for field in ONLINE_VALIDATION_FIELDS
                },
                "linked_stock_sku_rows": len(linked_rows),
                "unique_stock_sku_count": len(inventory_cache),
                "combination_stock_sku_count": len(combination_cache),
                "stock_state_counts": stock_state_counts,
                "unlinked_stock_sku_rows": len(online_rows) - len(linked_rows),
                "location_id_empty_count": sum(1 for row in linked_rows if _is_empty(row.get("locationId"))),
                "warehouse_empty_count": sum(1 for row in linked_rows if _is_empty(row.get("warehouse"))),
                "field_stats": field_stats,
            },
            ensure_ascii=False,
            indent=2,
        ),
        name="stockSku_inventory_master_field_cross_check",
        attachment_type=allure.attachment_type.JSON,
    )


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
@pytest.mark.parametrize("group_sku_id", COMBINATION_ITEM_IDS)
def test_combination_sku_returns_definition_and_components(sku_group_api, group_sku_id: str) -> None:
    """组合 SKU 查询应返回主记录和至少一个子 SKU 明细。"""
    body = sku_group_api.list_page(group_sku_id)
    sku_group_api.assert_success(body)
    rows = sku_group_api.rows(body)

    assert body["total"] == 1
    assert len(rows) == 1
    group = rows[0]
    assert str(group.get("groupSkuId")) == group_sku_id
    assert group.get("status") not in (None, "")
    assert isinstance(group.get("omsSkuGroupItemVoList"), list)

    components = group["omsSkuGroupItemVoList"]
    assert components, f"组合 SKU={group_sku_id} 缺少子 SKU"
    for component in components:
        assert str(component.get("groupSkuId")) == group_sku_id
        assert component.get("itemId") not in (None, "")
        assert _decimal(component, "itemQty") is not None


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_combination_sku_numeric_summary_fields_are_well_formed(sku_group_api) -> None:
    """组合 SKU 汇总库存字段应为数值，便于后续组合库存计算。"""
    for group_sku_id in COMBINATION_ITEM_IDS:
        body = sku_group_api.list_page(group_sku_id)
        sku_group_api.assert_success(body)
        group = sku_group_api.rows(body)[0]
        for field in ("totalItemQty", "groupStockQty", "groupInTransitQty"):
            assert _decimal(group, field) is not None, f"{group_sku_id} 的 {field} 非数值: {group}"

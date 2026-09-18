"""Regression tests for online product stock queries in the TEST environment."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import allure
import pytest

from modules.auto_test.api.inventory_variant_stock_api import InventoryVariantStockAPI

DATA_FILE = Path(__file__).resolve().parents[3] / "fixtures" / "inventory_variant_stock_test_data.json"
REQUIRED_FIELDS = ("productId", "variantId", "title")
NUMERIC_FIELDS = (
    "availableStock",
    "inboundStock",
    "pendingFulfillment",
    "actualAvailableStock",
    "projectedStock",
)
STOCK_STATES = {"0", "1", "2", "3", "4"}
SORT_CASES = (
    ("availableStock", "asc"),
    ("availableStock", "desc"),
    ("inboundStock", "asc"),
    ("inboundStock", "desc"),
    ("projectedStock", "asc"),
    ("projectedStock", "desc"),
)


@pytest.fixture(scope="module")
def stock_test_data() -> dict[str, Any]:
    with DATA_FILE.open(encoding="utf-8") as stream:
        data = json.load(stream)
    assert isinstance(data, dict)
    assert len(data["variants"]) == 20
    return data


@pytest.fixture(scope="function")
def stock_api(authenticated_http_client, api_base_url: str) -> InventoryVariantStockAPI:
    return InventoryVariantStockAPI(authenticated_http_client, api_base_url)


def _base_params(data: dict[str, Any]) -> dict[str, str]:
    return {
        "storeId": str(data["storeId"]),
        "customerId": str(data["customerId"]),
    }


def _product_params(data: dict[str, Any]) -> dict[str, str]:
    return {**_base_params(data), "productId": str(data["productId"]), "pageSize": "100", "pageNum": "1"}


def _variant_expectation(data: dict[str, Any], variant_id: str) -> dict[str, str]:
    return next(variant for variant in data["variants"] if variant["variantId"] == variant_id)


VARIANT_ITEM_CASES = tuple(
    (variant["variantId"], variant["itemId"])
    for variant in json.loads(DATA_FILE.read_text(encoding="utf-8"))["variants"]
)


def _row_fingerprint(row: dict[str, Any]) -> tuple[str, ...]:
    """Identify one returned stock row without assuming variant-to-SKU uniqueness."""
    return tuple(
        str(row.get(field, ""))
        for field in ("storeId", "productId", "variantId", "platformSku", "stockSku", "skuColorSize")
    )


def _all_product_rows(
    stock_api: InventoryVariantStockAPI,
    data: dict[str, Any],
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """Query every product page so output assertions are not limited to page one."""
    params = {
        **_base_params(data),
        "productId": str(data["productId"]),
        "pageSize": str(page_size),
        "pageNum": "1",
    }
    first_body = stock_api.query_page(params)
    first_envelope = stock_api.assert_success(first_body)
    total = first_envelope["total"]
    rows = list(stock_api.rows(first_body))
    page_count = max(1, (total + page_size - 1) // page_size)

    for page_num in range(2, page_count + 1):
        page_body = stock_api.query_page({**params, "pageNum": str(page_num)})
        stock_api.assert_success(page_body)
        rows.extend(stock_api.rows(page_body))

    assert len(rows) == total, f"商品库存分页结果不完整: total={total}, actual={len(rows)}"
    assert len(rows) == len({_row_fingerprint(row) for row in rows}), "商品库存分页存在重复记录"
    return rows


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.smoke
@pytest.mark.p0
def test_query_by_store_and_customer_returns_success_envelope(stock_api, stock_test_data) -> None:
    """店铺和客户条件可以访问接口并返回合法分页结构。"""
    body = stock_api.query_page({**_base_params(stock_test_data), "pageSize": "100", "pageNum": "1"})
    envelope = stock_api.assert_success(body)

    assert envelope["total"] >= 0
    for row in stock_api.rows(body):
        assert str(row.get("storeId")) == stock_test_data["storeId"]


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.smoke
@pytest.mark.p0
def test_query_by_product_returns_the_expected_variants(stock_api, stock_test_data) -> None:
    """商品精确查询不得串入其他商品，并应覆盖测试数据中的所有变体。"""
    rows = _all_product_rows(stock_api, stock_test_data)

    assert rows, "已提供的商品测试数据应至少返回一条变体"
    actual_variant_ids = {str(row["variantId"]) for row in rows}
    expected_variant_ids = {str(variant["variantId"]) for variant in stock_test_data["variants"]}

    assert actual_variant_ids, "商品查询应返回变体 ID"
    assert (
        expected_variant_ids <= actual_variant_ids
    ), f"商品全量分页未覆盖测试变体: missing={sorted(expected_variant_ids - actual_variant_ids)}"

    for row in rows:
        assert str(row["productId"]) == stock_test_data["productId"]
        assert row["title"] == stock_test_data["title"]


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
@pytest.mark.parametrize(
    "variant_id",
    [
        "46501778554982",
        "46501778522214",
        "46501778489446",
        "46501778456678",
        "46501778423910",
        "46501778391142",
        "46501778358374",
        "46501778325606",
        "46501778292838",
        "46501778260070",
        "46501778227302",
        "46501778194534",
        "46501778161766",
        "46501778128998",
        "46501778096230",
        "46501778063462",
        "46501778030694",
        "46501777997926",
        "46501777965158",
        "46501777932390",
    ],
)
def test_query_each_variant_by_exact_variant_id(stock_api, stock_test_data, variant_id: str) -> None:
    """20 个已知变体 ID 均可精确查询。"""
    body = stock_api.query_page({**_base_params(stock_test_data), "variantId": variant_id})
    stock_api.assert_success(body)
    rows = stock_api.rows(body)
    expected = _variant_expectation(stock_test_data, variant_id)

    assert rows, f"variantId={variant_id} 应至少返回一条变体记录"
    for row in rows:
        assert str(row["variantId"]) == variant_id
        assert str(row["productId"]) == stock_test_data["productId"]
        assert row["title"] == stock_test_data["title"]
        if row.get("platformSku") not in (None, ""):
            assert str(row["platformSku"]) == expected["platformSku"]


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
@pytest.mark.parametrize("variant_id,item_id", VARIANT_ITEM_CASES)
def test_query_each_matched_item_id_returns_the_bound_stock_sku(
    stock_api,
    stock_test_data,
    variant_id: str,
    item_id: str,
) -> None:
    """每个已匹配的 ERP itemId 都应按精确条件返回对应 stockSku。"""
    body = stock_api.query_page({**_base_params(stock_test_data), "itemId": item_id})
    stock_api.assert_success(body)
    rows = stock_api.rows(body)

    assert rows, f"itemId={item_id} 应至少返回一条库存记录，接口响应: {json.dumps(body, ensure_ascii=False)}"
    assert any(str(row.get("variantId")) == variant_id for row in rows)
    assert all(str(row.get("stockSku")) == item_id for row in rows)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
@pytest.mark.parametrize(
    "platform_sku",
    [
        "Inventory_sync_00245",
        "Inventory_sync_00240",
        "Inventory_sync_00235",
        "Inventory_sync_00230",
        "Inventory_sync_00226",
    ],
)
def test_query_by_platform_sku_fuzzy_match(stock_api, stock_test_data, platform_sku: str) -> None:
    """平台 SKU 支持按文档声明的模糊匹配。"""
    body = stock_api.query_page({**_base_params(stock_test_data), "platformSku": platform_sku})
    stock_api.assert_success(body)
    rows = stock_api.rows(body)

    assert rows, f"platformSku={platform_sku} 应有匹配数据"
    for row in rows:
        assert platform_sku.lower() in str(row.get("platformSku", "")).lower()


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_query_by_title_is_case_insensitive(stock_api, stock_test_data) -> None:
    """标题查询应支持忽略大小写的模糊匹配。"""
    body = stock_api.query_page({**_base_params(stock_test_data), "title": "inventory_sync"})
    stock_api.assert_success(body)
    rows = stock_api.rows(body)

    assert rows
    assert all("inventory_sync" in str(row.get("title", "")).lower() for row in rows)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
@pytest.mark.parametrize("stock_status", sorted(STOCK_STATES))
def test_query_by_stock_status_only_returns_the_requested_state(
    stock_api,
    stock_test_data,
    stock_status: str,
) -> None:
    """库存状态过滤只允许返回请求的状态；某状态无数据时保留为空结果。"""
    body = stock_api.query_page(
        {
            **_base_params(stock_test_data),
            "stockStatus": stock_status,
            "pageSize": "100",
            "pageNum": "1",
        }
    )
    stock_api.assert_success(body)
    rows = stock_api.rows(body)

    assert all(str(row.get("stockState")) == stock_status for row in rows)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
@pytest.mark.parametrize("order_by_column,direction", SORT_CASES)
def test_query_sorting_honors_supported_field_and_direction(
    stock_api,
    stock_test_data,
    order_by_column: str,
    direction: str,
) -> None:
    """支持的库存字段和升降序参数应影响返回行的数值顺序。"""
    body = stock_api.query_page(
        {
            **_product_params(stock_test_data),
            "orderByColumn": [order_by_column],
            "isAsc": [direction],
        }
    )
    stock_api.assert_success(body)
    rows = stock_api.rows(body)
    assert rows

    values = [Decimal(str(row[order_by_column])) for row in rows]
    expected = sorted(values, reverse=direction == "desc")
    assert values == expected, f"{order_by_column} {direction} 排序不符合预期: {values}"


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_warehouse_parameter_is_reserved_and_does_not_filter_rows(stock_api, stock_test_data) -> None:
    """当前版本 warehouse 为预留参数，传入不存在的仓库也不应改变聚合结果。"""
    baseline = stock_api.query_page(_product_params(stock_test_data))
    reserved = stock_api.query_page({**_product_params(stock_test_data), "warehouse": "__not_existing__"})
    stock_api.assert_success(baseline)
    stock_api.assert_success(reserved)

    def normalized_rows(body: dict[str, Any]) -> list[str]:
        stable_rows = []
        for row in stock_api.rows(body):
            normalized = dict(row)
            normalized.pop("stockUpdateTime", None)
            stable_rows.append(json.dumps(normalized, ensure_ascii=False, sort_keys=True))
        return sorted(stable_rows)

    assert normalized_rows(reserved) == normalized_rows(baseline)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_query_pagination_has_no_duplicate_variants(stock_api, stock_test_data) -> None:
    """商品库存全量分页时不应重复、漏数或串入其他商品。"""
    rows = _all_product_rows(stock_api, stock_test_data, page_size=20)

    assert rows, "分页查询应返回至少一条商品库存记录"
    assert all(str(row["productId"]) == stock_test_data["productId"] for row in rows)


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_query_nonexistent_product_returns_empty_rows(stock_api, stock_test_data) -> None:
    """不存在的商品不应返回其他商品数据。"""
    body = stock_api.query_page({**_base_params(stock_test_data), "productId": "999999999999999999"})
    envelope = stock_api.assert_success(body)
    assert envelope["rows"] == []
    assert envelope["total"] == 0


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
def test_query_response_schema_and_required_fields(stock_api, stock_test_data) -> None:
    """返回字段和库存数值字段符合接口文档。"""
    body = stock_api.query_page(_product_params(stock_test_data))
    stock_api.assert_success(body)
    rows = stock_api.rows(body)
    assert rows

    for row in rows:
        for field in REQUIRED_FIELDS:
            assert row.get(field) not in (None, ""), f"{field} 不应为空: {row}"
            assert isinstance(row[field], str), f"{field} 应为字符串: {row}"

        for field in ("stockSku", "platformSku", "skuColorSize", "stockState", "warehouse"):
            if field in row and row[field] is not None:
                assert isinstance(row[field], str), f"{field} 应为字符串: {row}"

        for field in NUMERIC_FIELDS:
            assert field in row, f"响应缺少库存字段 {field}: {row}"
            assert isinstance(row[field], (int, float)), f"{field} 应为数值: {row}"

        if row.get("stockState") not in (None, ""):
            assert str(row["stockState"]) in STOCK_STATES

    allure.attach(
        json.dumps({"total": body.get("total"), "sample": rows[:2]}, ensure_ascii=False, indent=2),
        name="库存查询响应样例",
        attachment_type=allure.attachment_type.JSON,
    )


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p0
def test_full_product_output_contract_and_stock_formulas_across_pages(stock_api, stock_test_data) -> None:
    """全分页逐条校验必填字段、状态枚举、数值类型和库存计算公式。"""
    rows = _all_product_rows(stock_api, stock_test_data)
    assert rows

    for row in rows:
        for field in REQUIRED_FIELDS:
            assert row.get(field) not in (None, ""), f"{field} 不应为空: {row}"
            assert isinstance(row[field], str), f"{field} 应为字符串: {row}"

        for field in NUMERIC_FIELDS:
            assert field in row, f"响应缺少库存字段 {field}: {row}"
            assert isinstance(row[field], (int, float)), f"{field} 应为数值: {row}"

        assert str(row.get("stockState")) in STOCK_STATES, f"stockState 非法: {row}"
        actual_available = Decimal(str(row["availableStock"])) - Decimal(str(row["pendingFulfillment"]))
        projected_stock = (
            Decimal(str(row["availableStock"]))
            + Decimal(str(row["inboundStock"]))
            - Decimal(str(row["pendingFulfillment"]))
        )
        assert Decimal(str(row["actualAvailableStock"])) == actual_available
        assert Decimal(str(row["projectedStock"])) == projected_stock


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.p1
def test_inventory_stock_calculations_are_consistent(stock_api, stock_test_data) -> None:
    """校验实际库存和预计库存的接口计算公式。"""
    body = stock_api.query_page(_product_params(stock_test_data))
    stock_api.assert_success(body)
    rows = stock_api.rows(body)
    assert rows

    for row in rows:
        actual_available = Decimal(str(row["availableStock"])) - Decimal(str(row["pendingFulfillment"]))
        projected_stock = (
            Decimal(str(row["availableStock"]))
            + Decimal(str(row["inboundStock"]))
            - Decimal(str(row["pendingFulfillment"]))
        )
        assert Decimal(str(row["actualAvailableStock"])) == actual_available
        assert Decimal(str(row["projectedStock"])) == projected_stock

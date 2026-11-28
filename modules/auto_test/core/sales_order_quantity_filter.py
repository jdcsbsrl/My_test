"""Business assertions for sales-order quantity filters (requirement 1003845)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OrderProductMetrics:
    sku_types: int
    total_quantity: int


def order_product_metrics(items: list[dict[str, Any]]) -> OrderProductMetrics:
    """Count top-level order products and their quantities."""

    product_keys: set[str] = set()
    total_quantity = 0
    for index, item in enumerate(items):
        details = item.get("detail")
        products = details if isinstance(details, list) and details else [item]
        for detail_index, product in enumerate(products):
            key = product.get("itemId") or product.get("sellerSku") or f"item:{index}:{detail_index}"
            quantity = product.get("quantity")
            if quantity is None:
                quantity = product.get("platformQuantity")
            product_keys.add(str(key))
            total_quantity += int(quantity or 0)
    return OrderProductMetrics(sku_types=len(product_keys), total_quantity=total_quantity)


def metrics_by_order(item_payload: dict[str, Any]) -> dict[str, OrderProductMetrics]:
    data = item_payload.get("data")
    if not isinstance(data, dict):
        raise AssertionError("订单明细接口未返回按订单号分组的data对象")
    return {str(order_no): order_product_metrics(items) for order_no, items in data.items() if isinstance(items, list)}

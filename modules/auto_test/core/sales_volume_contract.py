"""Shared, side-effect-free rules for the merged product sales report."""

from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

DIMENSIONS = {
    "sku": "queryOmsInventoryNew",
    "store": "queryStoreSalesDimensionReport",
    "warehouse": "queryWarehouseSalesDimensionReport",
    "country": "queryCountrySalesDimensionReport",
    "category": "queryCategorySalesDimensionReport",
}


def build_filter(
    pay_range: Sequence[str] | None = None,
    ship_range: Sequence[str] | None = None,
    store_ids: Iterable[str] = (),
    create_range: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build the common request fields without inferring a six-month boundary."""
    if pay_range is None and ship_range is None:
        raise ValueError("A payment or shipping time range is required")
    payload: dict[str, Any] = {
        "classIds": [],
        "customClassIds": [],
        "salesStatuses": [],
        "creatorIds": [],
        "storeIds": list(store_ids),
    }
    for name, value in (("payTime", pay_range), ("sendDate", ship_range), ("createTime", create_range)):
        if value is None:
            continue
        if len(value) != 2:
            raise ValueError("A time range requires both endpoints")
        start, end = value
        if datetime.fromisoformat(start) > datetime.fromisoformat(end):
            raise ValueError("Time range start must not exceed end")
        payload[name + "Begin"] = start
        payload[name + "End"] = end
    return payload


def group_sales_by_sku(
    rows: Iterable[Mapping[str, Any]], sku_key: str = "itemId", sales_key: str = "salesNumber"
) -> dict[str, Decimal]:
    """Sum flattened dimension details using decimal arithmetic."""
    totals: defaultdict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        sku = row.get(sku_key)
        if not sku:
            raise ValueError("Missing SKU in report detail")
        totals[str(sku)] += Decimal(str(row.get(sales_key) or 0))
    return dict(totals)


def order_item_rows(groups: Iterable[Mapping[str, Any]]) -> Iterator[Mapping[str, Any]]:
    """Yield actual order items, including children of bundled SKU groups."""
    for group in groups:
        children = group.get("detail")
        yield from children if isinstance(children, list) else [group]


def aggregate_orders(
    orders: Iterable[Mapping[str, Any]], items_by_order: Mapping[str, list[Mapping[str, Any]]]
) -> dict[str, dict[str, int]]:
    """Aggregate valid orders by SKU; an order is counted once per SKU."""
    sales: defaultdict[str, int] = defaultdict(int)
    order_numbers: defaultdict[str, set[str]] = defaultdict(set)
    for order in orders:
        order_no = str(order.get("orderNo") or "")
        if not order_no:
            raise ValueError("Order number is required for distinct counting")
        if str(order.get("orderStatus")) == "6":
            continue
        if order_no not in items_by_order:
            raise ValueError(f"Missing order details for {order_no}")
        for item in order_item_rows(items_by_order[order_no] or []):
            sku = item.get("itemId")
            quantity = int(item.get("quantity") or 0)
            if sku and quantity > 0:
                sales[str(sku)] += quantity
                order_numbers[str(sku)].add(order_no)
    return {sku: {"sales": total, "orders": len(order_numbers[sku])} for sku, total in sales.items()}


def category_order_counts(
    orders: Iterable[Mapping[str, Any]],
    items_by_order: Mapping[str, list[Mapping[str, Any]]],
    sku_categories: Mapping[str, str],
) -> dict[str, int]:
    """Count each order once per category even if it has multiple SKUs."""
    grouped: defaultdict[str, set[str]] = defaultdict(set)
    for order in orders:
        order_no = str(order.get("orderNo") or "")
        if not order_no:
            raise ValueError("Order number is required for distinct counting")
        if str(order.get("orderStatus")) == "6":
            continue
        if order_no not in items_by_order:
            raise ValueError(f"Missing order details for {order_no}")
        for item in order_item_rows(items_by_order[order_no] or []):
            sku = str(item.get("itemId") or "")
            if sku and int(item.get("quantity") or 0) > 0:
                if sku not in sku_categories:
                    raise ValueError(f"Missing category for SKU {sku}")
                grouped[sku_categories[sku]].add(order_no)
    return {category: len(order_ids) for category, order_ids in grouped.items()}


def find_task_by_marker(
    fetch_page: Callable[[int, int], Mapping[str, Any]],
    marker: str,
    page_size: int = 100,
    max_pages: int = 200,
) -> Mapping[str, Any] | None:
    """Search every reported task page; incomplete pagination is an error."""
    matches = []
    for page in range(1, max_pages + 1):
        body = fetch_page(page, page_size)
        if body.get("code") != 200 or not isinstance(body.get("total"), int):
            raise ValueError("Task list returned an invalid response")
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("Task list rows must be a list")
        matches.extend(row for row in rows if row.get("taskDesc") == marker)
        if len(matches) > 1:
            raise ValueError("Task marker matched more than one task")
        if page * page_size >= body["total"]:
            return matches[0] if matches else None
        if not rows:
            raise ValueError("Task pagination ended before the reported total")
    raise ValueError("Task pagination exceeded its safety limit")

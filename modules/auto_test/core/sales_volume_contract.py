"""Shared, side-effect-free rules for the merged product sales report."""

import base64
import json
from calendar import monthrange
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

DIMENSIONS = {
    "sku": "queryOmsInventoryNew",
    "store": "queryStoreSalesDimensionReport",
    "warehouse": "queryWarehouseSalesDimensionReport",
    "country": "queryCountrySalesDimensionReport",
    "category": "queryCategorySalesDimensionReport",
}

DIMENSION_LABELS = {
    "sku": "SKU维度",
    "store": "店铺维度",
    "warehouse": "发货仓库维度",
    "country": "国家维度",
    "category": "类目维度",
}


def build_export_task_name(dimension: str) -> str:
    """Return the ERP default prefix; the server appends the creation timestamp."""
    try:
        label = DIMENSION_LABELS[dimension]
    except KeyError as exc:
        raise ValueError(f"Unsupported sales report dimension: {dimension}") from exc
    return f"商品销量报表_{label}"


def build_completed_report_window(as_of_date: date | str | None = None, days: int = 30) -> tuple[str, str]:
    """Build a report window from completed calendar days only.

    ``as_of_date`` is the run's shared anchor date. The window ends the day
    before that anchor so current-day orders cannot move a reconciliation.
    """
    if days < 1:
        raise ValueError("The completed report window must contain at least one day")
    if isinstance(as_of_date, str):
        try:
            as_of_date = date.fromisoformat(as_of_date.strip())
        except ValueError as exc:
            raise ValueError("The report window anchor must use YYYY-MM-DD") from exc
    elif as_of_date is None:
        as_of_date = date.today()
    elif not isinstance(as_of_date, date):
        raise ValueError("The report window anchor must be a date or YYYY-MM-DD string")

    end_date = as_of_date - timedelta(days=1)
    start_date = end_date - timedelta(days=days - 1)
    return (
        f"{start_date:%Y-%m-%d} 00:00:00",
        f"{end_date:%Y-%m-%d} 23:59:59",
    )


def build_report_sample_history_windows(
    report_window: Sequence[str], lookback_months: int = 6, chunk_days: int = 30
) -> list[tuple[str, str]]:
    """Return contiguous, bounded windows before the report window.

    The combined history and report window never reaches farther back than
    ``lookback_months`` calendar months. Older history is split into chunks so
    order-source sample discovery does not issue one request per day.
    """
    if len(report_window) != 2:
        raise ValueError("A report window requires both endpoints")
    if lookback_months < 1 or chunk_days < 1:
        raise ValueError("Lookback months and chunk days must be positive")

    report_start = datetime.fromisoformat(report_window[0])
    report_end = datetime.fromisoformat(report_window[1])
    if report_start > report_end:
        raise ValueError("Report window start must not exceed end")

    month_index = report_end.year * 12 + report_end.month - 1 - lookback_months
    start_year, start_month_index = divmod(month_index, 12)
    start_month = start_month_index + 1
    history_start_day = min(report_end.day, monthrange(start_year, start_month)[1])
    history_start = date(start_year, start_month, history_start_day)

    cursor_end = report_start.date() - timedelta(days=1)
    if cursor_end < history_start:
        return []

    windows = []
    while cursor_end >= history_start:
        cursor_start = max(history_start, cursor_end - timedelta(days=chunk_days - 1))
        windows.append(
            (
                datetime.combine(cursor_start, time.min).strftime("%Y-%m-%d %H:%M:%S"),
                datetime.combine(cursor_end, time(23, 59, 59)).strftime("%Y-%m-%d %H:%M:%S"),
            )
        )
        cursor_end = cursor_start - timedelta(days=1)
    return windows


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
    """Yield active order items, omitting platform-removed lines."""
    for group in groups:
        if _is_removed_order_item(group):
            continue
        children = group.get("detail")
        items = children if isinstance(children, list) else [group]
        yield from (item for item in items if not _is_removed_order_item(item))


def bundle_order_rows(
    orders: Iterable[Mapping[str, Any]],
    items_by_order: Mapping[str, list[Mapping[str, Any]]],
) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """Return non-void order groups with expanded bundle component rows."""
    bundles = []
    for order in orders:
        order_no = str(order.get("orderNo") or "")
        if not order_no or str(order.get("orderStatus")) == "6":
            continue
        for row in items_by_order.get(order_no, []):
            if _is_removed_order_item(row):
                continue
            children = row.get("detail")
            if isinstance(children, list) and any(
                isinstance(child, Mapping) and not _is_removed_order_item(child) for child in children
            ):
                bundles.append((order, row))
    return bundles


def _is_removed_order_item(item: Mapping[str, Any]) -> bool:
    """Identify soft-removed marketplace lines still returned by order APIs."""
    change_type = str(item.get("platformChangeType") or "").strip().casefold()
    remove_tag = item.get("showRemoveTag")
    return change_type == "removed" or remove_tag is True or str(remove_tag).strip().casefold() in {"1", "true"}


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


def order_source_breakdown(
    orders: Iterable[Mapping[str, Any]],
    items_by_order: Mapping[str, list[Mapping[str, Any]]],
    item_ids: Iterable[str],
) -> dict[str, list[dict[str, Any]]]:
    """Return per-order source lines for SKUs with a reconciliation mismatch."""
    targets = {str(item_id) for item_id in item_ids}
    breakdown: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for order in orders:
        order_no = str(order.get("orderNo") or "")
        if not order_no or str(order.get("orderStatus")) == "6":
            continue
        for group in items_by_order.get(order_no, []):
            if _is_removed_order_item(group):
                continue
            children = group.get("detail")
            item_rows = children if isinstance(children, list) else [group]
            for item in item_rows:
                if _is_removed_order_item(item):
                    continue
                item_id = str(item.get("itemId") or "")
                quantity = int(item.get("quantity") or 0)
                if item_id not in targets or quantity <= 0:
                    continue
                line: dict[str, Any] = {
                    "orderNo": order_no,
                    "orderStatus": str(order.get("orderStatus") or ""),
                    "itemId": item_id,
                    "quantity": quantity,
                }
                for field in ("payTime", "storeId"):
                    value = order.get(field)
                    if value is not None:
                        line[field] = value
                if isinstance(children, list):
                    group_sku_id = group.get("groupSkuId") or group.get("itemId")
                    if group_sku_id:
                        line["groupSkuId"] = str(group_sku_id)
                breakdown[item_id].append(line)
    return dict(breakdown)


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


def list_export_tasks(
    fetch_page: Callable[[int, int], Mapping[str, Any]],
    page_size: int = 100,
    max_pages: int = 200,
) -> list[Mapping[str, Any]]:
    """Read every reported export-task page; incomplete pagination is an error."""
    tasks = []
    for page in range(1, max_pages + 1):
        body = fetch_page(page, page_size)
        if body.get("code") != 200 or not isinstance(body.get("total"), int):
            raise ValueError("Task list returned an invalid response")
        rows = body.get("rows") or []
        if not isinstance(rows, list):
            raise ValueError("Task list rows must be a list")
        tasks.extend(rows)
        if page * page_size >= body["total"]:
            if len(tasks) < body["total"]:
                raise ValueError("Task pagination ended before the reported total")
            return tasks
        if not rows:
            raise ValueError("Task pagination ended before the reported total")
    raise ValueError("Task pagination exceeded its safety limit")


def export_task_id(task: Mapping[str, Any]) -> str:
    """Return an export task's stable identifier from supported API field names."""
    for key in ("id", "taskId", "exportTaskId"):
        value = task.get(key)
        if value not in (None, ""):
            return str(value)
    raise ValueError("Export task row is missing its task ID")


def token_user_id(token: str) -> str | None:
    """Extract a user identifier claim without exposing or persisting the token."""
    parts = str(token or "").strip().split(".")
    if len(parts) < 2:
        return None
    encoded_payload = parts[1]
    try:
        payload = json.loads(base64.urlsafe_b64decode(encoded_payload + "=" * (-len(encoded_payload) % 4)))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    for key in ("userId", "user_id", "uid", "sub"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _task_conditions(task: Mapping[str, Any]) -> Mapping[str, Any] | None:
    conditions = task.get("taskConditions")
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except (ValueError, TypeError, json.JSONDecodeError):
            return None
    return conditions if isinstance(conditions, Mapping) else None


def find_new_export_task(
    fetch_page: Callable[[int, int], Mapping[str, Any]],
    task_name_prefix: str,
    previous_task_ids: set[str],
    page_size: int = 100,
    max_pages: int = 200,
    creator_id: str | None = None,
    expected_task_conditions: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    """Find a new default-named task using creator and condition correlation when provided."""
    tasks = list_export_tasks(fetch_page, page_size=page_size, max_pages=max_pages)
    matches = []
    for task in tasks:
        task_name = str(task.get("taskName") or "")
        if (task_name == task_name_prefix or task_name.startswith(task_name_prefix + "_")) and export_task_id(
            task
        ) not in previous_task_ids:
            if creator_id is not None and str(task.get("createBy") or "") != str(creator_id):
                continue
            if expected_task_conditions is not None and _task_conditions(task) != expected_task_conditions:
                continue
            matches.append(task)
    if len(matches) > 1:
        summaries = [
            {
                "id": export_task_id(task),
                "taskName": task.get("taskName"),
                "createBy": task.get("createBy"),
                "createTime": task.get("createTime"),
            }
            for task in matches
        ]
        raise ValueError(f"More than one new export task matched the requested creator and conditions: {summaries}")
    return matches[0] if matches else None

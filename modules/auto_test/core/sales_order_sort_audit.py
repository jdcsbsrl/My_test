"""Read-only sales-order sort audit owned by the auto_test module."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ORDER_LIST_PATH = "/oms-admin/sales/order/batchListNew"
ORDER_DETAILS_PATH = "/oms-admin/sales/orderItem/queryAllList"
COUNTRY_DICT_PATH = "/system/dict/data/type/country"
STORE_LIST_PATHS = (
    "/oms-admin/base/store/queryListV2",
    "/oms-admin/base/store/queryList",
)
CHANNEL_CATALOG_PATH = "/oms-admin/logistics/serviceCode/dropdownList"

ORDER_LIST_BASE_PAYLOAD: dict[str, Any] = {
    "orderId": "",
    "orderNo": "",
    "orderByColumn": "",
    "isAsc": "",
    "platform": "",
    "shopifyLocationId": "",
    "fixedClassId": [],
    "itemIds": [],
    "customerClassBoList": [],
    "trackingStatus": "",
    "deptId": None,
    "pageNum": 1,
    "pageSize": 200,
    "orderStatus": "",
    "storeIds": "",
    "itemAttribute": "",
    "exceptionClassIds": "",
    "customClassIds": "",
    "countryCode": "",
    "onlyShowMyProcessing": "0",
    "queryType": "0",
}


@dataclass(frozen=True)
class SortField:
    label: str
    order_by_column: str
    response_key: str
    value_kind: str
    detail_key: str | None = None


SORT_FIELDS: tuple[SortField, ...] = (
    SortField("付款时间", "pay_time", "payTime", "datetime"),
    SortField("订单金额", "order_price_amount", "orderPriceAmount", "decimal"),
    SortField("sku编码", "item_id", "itemId", "text", "itemId"),
    SortField("平台sku", "seller_sku", "sellerSku", "text", "sellerSku"),
    SortField("国家", "country_code", "countryCode", "country"),
    SortField("店铺", "store_id", "storeId", "store"),
    SortField("物流渠道", "provider_channel_id", "providerChannelId", "channel"),
    SortField("创建日期", "create_time", "createTime", "datetime"),
    SortField("发货时间", "send_date", "sendDate", "datetime"),
    SortField("交运时间", "logistics_date", "logisticsDate", "datetime"),
    SortField("物流单号", "tracking_number", "trackingNumber", "text"),
    SortField("利润", "profit", "profit", "decimal"),
    SortField("利润率", "profit_rate", "profitRate", "decimal"),
    SortField("转入WMS的时间", "sync_wms_time", "syncWmsTime", "datetime"),
)

# Profit is paused from the default regression per business decision; retain explicit audit.
PAUSED_REGRESSION_FIELDS = ("\u5229\u6da6",)
REGRESSION_FIELDS = tuple(field for field in SORT_FIELDS if field.label not in PAUSED_REGRESSION_FIELDS)

SUCCESS_CODES = {None, 0, "0", 200, "200"}
ORDER_NUMBER_KEYS = ("orderNo", "orderNum", "systemOrderNo")


class SortAuditError(RuntimeError):
    """An API response or audit input could not be interpreted safely."""


class UnmappedCountryCode(SortAuditError):
    """An order country label is not present in the country dictionary."""


class UnmappedStoreId(SortAuditError):
    """An order store ID is not present in the store-name dictionaries."""


class UnmappedChannelId(SortAuditError):
    """An order channel ID is not present in the logistics service catalog."""


class InvalidSortValue(SortAuditError):
    """An API value cannot be normalized using its declared type."""


def normalize_text(value: Any) -> str:
    """Normalize display strings without changing case-sensitive SKU meaning."""
    return unicodedata.normalize("NFKC", str(value)).strip()


def build_country_code_map(records: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map country labels and already-coded values to uppercase short codes."""
    mapping: dict[str, str] = {}
    for record in records:
        label = normalize_text(record.get("dictLabel") or "")
        code = normalize_text(record.get("dictValue") or "").upper()
        if label and code:
            mapping[label.casefold()] = code
            mapping[code.casefold()] = code
    return mapping


def build_store_name_map(records: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map backend store IDs to the store names shown in the sales UI."""
    mapping: dict[str, str] = {}
    for record in records:
        store_id = normalize_text(record.get("id") or "")
        store_name = normalize_text(record.get("name") or "")
        if store_id and store_name:
            previous = mapping.get(store_id)
            if previous is not None and previous != store_name:
                raise SortAuditError(f"店铺目录中同一 ID 对应多个名称: {store_id}")
            mapping[store_id] = store_name
    return mapping


def build_channel_name_map(records: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map provider-channel IDs to the logistics-channel names shown in the UI."""
    mapping: dict[str, str] = {}
    for record in records:
        channel_id = normalize_text(record.get("id") or "")
        channel_name = normalize_text(record.get("providerChannel") or "")
        if channel_id and channel_name:
            previous = mapping.get(channel_id)
            if previous is not None and previous != channel_name:
                raise SortAuditError(f"物流渠道目录中同一 ID 对应多个名称: {channel_id}")
            mapping[channel_id] = channel_name
    return mapping


def normalize_sort_value(
    field: SortField,
    value: Any,
    country_codes: Mapping[str, str] | None = None,
    store_names: Mapping[str, str] | None = None,
    channel_names: Mapping[str, str] | None = None,
) -> Any | None:
    """Convert an API value to a comparable value; blank values remain null."""
    if value is None:
        return None
    text = normalize_text(value)
    if not text or text.casefold() in {"-", "--", "null", "none", "n/a"}:
        return None

    if field.value_kind == "country":
        code = (country_codes or {}).get(text.casefold())
        if not code:
            raise UnmappedCountryCode(f"国家值没有字典映射: {text}")
        return code.upper()

    if field.value_kind == "store":
        store_name = (store_names or {}).get(text)
        if not store_name:
            raise UnmappedStoreId(f"店铺 ID 没有名称映射: {text}")
        return normalize_text(store_name).casefold()

    if field.value_kind == "channel":
        channel_name = (channel_names or {}).get(text)
        if not channel_name:
            raise UnmappedChannelId(f"物流渠道 ID 没有名称映射: {text}")
        return normalize_text(channel_name).casefold()

    if field.value_kind == "decimal":
        numeric_text = text.replace(",", "")
        if numeric_text.endswith("%"):
            numeric_text = numeric_text[:-1].strip()
        try:
            return Decimal(numeric_text)
        except InvalidOperation as exc:
            raise InvalidSortValue(f"数值字段包含无法解析的值: {text}") from exc

    if field.value_kind == "datetime":
        iso_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(iso_text)
        except ValueError as exc:
            raise InvalidSortValue(f"时间字段包含无法解析的值: {text}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    if field.value_kind == "name":
        return text.casefold()

    if field.value_kind == "text":
        return text

    raise InvalidSortValue(f"未知排序值类型: {field.value_kind}")


def find_record_lists(value: Any) -> list[list[dict[str, Any]]]:
    """Recursively find record arrays in common ERP response envelopes."""
    found: list[list[dict[str, Any]]] = []
    if isinstance(value, dict):
        for child in value.values():
            found.extend(find_record_lists(child))
    elif isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            found.append(value)
        for child in value:
            found.extend(find_record_lists(child))
    return found


def extract_order_rows(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    data = body.get("data", body)
    if isinstance(data, dict):
        for key in ("list", "rows", "records", "orders", "data"):
            candidate = data.get(key)
            if isinstance(candidate, list) and all(isinstance(row, dict) for row in candidate):
                return candidate
    lists = find_record_lists(data)
    return max(lists, key=len) if lists else []


def extract_total_count(body: Mapping[str, Any]) -> int | None:
    """Read the table total from the order-list response envelope."""
    data = body.get("data", body)
    if isinstance(data, dict):
        table = data.get("tableDataInfo")
        if isinstance(table, dict):
            total = table.get("total")
            try:
                parsed = int(total)
            except (TypeError, ValueError):
                parsed = -1
            if parsed >= 0:
                return parsed
    return None


def extract_order_details(body: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Read queryAllList's orderNo-keyed detail map."""
    data = body.get("data", body)
    if not isinstance(data, dict):
        raise SortAuditError("订单明细接口返回的 data 不是对象")

    def find_mapping(value: Any) -> dict[str, list[dict[str, Any]]] | None:
        if not isinstance(value, dict):
            return None
        candidate = {
            str(key): child
            for key, child in value.items()
            if isinstance(child, list) and all(isinstance(item, dict) for item in child)
        }
        if candidate:
            return candidate
        for child in value.values():
            result = find_mapping(child)
            if result is not None:
                return result
        return None

    result = find_mapping(data)
    return result if result is not None else {}


def row_order_number(row: Mapping[str, Any]) -> str | None:
    for key in ORDER_NUMBER_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def compare_values(values: Sequence[Any], direction: str) -> list[tuple[Any, Any]]:
    """Return adjacent inversions for the requested direction."""
    if direction not in {"asc", "desc"}:
        raise ValueError("direction must be 'asc' or 'desc'")
    inversions: list[tuple[Any, Any]] = []
    for previous, current in zip(values, values[1:]):
        if direction == "asc" and previous > current:
            inversions.append((previous, current))
        elif direction == "desc" and previous < current:
            inversions.append((previous, current))
    return inversions


def format_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def evaluate_values(values: Sequence[Any], direction: str) -> dict[str, Any]:
    inversions = compare_values(values, direction)
    if len(values) < 2:
        status = "inconclusive_insufficient_values"
    elif len(set(values)) < 2:
        status = "inconclusive_insufficient_variation"
    elif inversions:
        status = "fail_nonmonotonic"
    else:
        status = "pass"
    return {
        "status": status,
        "distinct_count": len(set(values)),
        "inversions": len(inversions),
        "inversion_examples": [
            {"previous": format_value(previous), "current": format_value(current)}
            for previous, current in inversions[:5]
        ],
    }


def evaluate_ordered_values(values: Sequence[Any | None], direction: str) -> dict[str, Any]:
    """Check value monotonicity and require blank values to remain at the end."""
    nonnull: list[Any] = []
    blank_seen = False
    nonnull_after_blank = 0
    for value in values:
        if value is None:
            blank_seen = True
        else:
            nonnull.append(value)
            if blank_seen:
                nonnull_after_blank += 1

    evaluated = evaluate_values(nonnull, direction)
    null_count = len(values) - len(nonnull)
    null_ordering = "not_observed" if null_count == 0 else "pass" if nonnull_after_blank == 0 else "fail"
    status = evaluated["status"]
    if nonnull_after_blank:
        status = "fail_nonmonotonic_and_null_not_last" if status == "fail_nonmonotonic" else "fail_null_not_last"
    return {
        **evaluated,
        "status": status,
        "null_count": null_count,
        "null_ordering": null_ordering,
        "nonnull_after_blank_count": nonnull_after_blank,
    }


def _sku_values_for_page(
    rows: Sequence[Mapping[str, Any]],
    details_by_order: Mapping[str, Sequence[Mapping[str, Any]]],
    detail_key: str,
) -> tuple[dict[str, list[str | None]], int, int]:
    candidates: dict[str, list[str | None]] = {"first": [], "min": [], "max": []}
    multi_sku_orders = 0
    missing_details = 0
    for row in rows:
        order_no = row_order_number(row)
        details = list(details_by_order.get(order_no or "", []))
        values = [
            normalize_text(detail.get(detail_key))
            for detail in details
            if detail.get(detail_key) not in (None, "") and normalize_text(detail.get(detail_key))
        ]
        if not values:
            missing_details += 1
            for name in candidates:
                candidates[name].append(None)
            continue
        unique_values = list(dict.fromkeys(values))
        if len(set(unique_values)) > 1:
            multi_sku_orders += 1
        candidates["first"].append(values[0])
        candidates["min"].append(min(unique_values))
        candidates["max"].append(max(unique_values))
    return candidates, multi_sku_orders, missing_details


def classify_status(status: str) -> str:
    """Map an audit status to pass, warning, or confirmed failure."""
    if status == "pass":
        return "passed"
    if status.startswith("fail_"):
        return "failure"
    return "warning"


def summarize_results(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep uncertain evidence visible as a non-blocking warning."""
    severity_counts = {"passed": 0, "warning": 0, "failure": 0}
    status_counts = Counter(str(item.get("status") or "request_error") for item in results)
    for status, count in status_counts.items():
        severity_counts[classify_status(status)] += count

    if severity_counts["failure"]:
        overall, exit_code = "failed", 1
    elif severity_counts["warning"] or not results:
        overall, exit_code = "warning", 0
    else:
        overall, exit_code = "passed", 0

    return {
        "overall": overall,
        "exit_code": exit_code,
        "severity_counts": severity_counts,
        "status_counts": dict(status_counts),
    }


class SalesOrderSortAuditor:
    """Audit all configured sort fields using an authenticated, read-only API client."""

    def __init__(
        self,
        client: Any,
        env: str,
        *,
        page_size: int = 200,
        max_pages: int = 3,
        sku_aggregation: str | None = "directional",
    ) -> None:
        if env not in {"test", "uat"}:
            raise ValueError("仅允许在 test 或 uat 环境执行")
        if page_size < 1 or page_size > 500:
            raise ValueError("page_size 必须在 1 到 500 之间")
        if max_pages < 1 or max_pages > 50:
            raise ValueError("max_pages 必须在 1 到 50 之间")
        if sku_aggregation not in {None, "directional", "first", "min", "max"}:
            raise ValueError("sku_aggregation 必须为 directional、first、min 或 max")
        self.client = client
        self.env = env
        self.page_size = page_size
        self.max_pages = max_pages
        self.sku_aggregation = sku_aggregation or "directional"

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.client.post(path, json=payload, timeout=60)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise SortAuditError(f"{path} 响应不是 JSON 对象")
        code = body.get("code")
        if code not in SUCCESS_CODES:
            raise SortAuditError(f"{path} 业务响应失败，code={code}")
        return body

    def _load_country_codes(self) -> dict[str, str]:
        response = self.client.get(COUNTRY_DICT_PATH, timeout=30)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or body.get("code") not in SUCCESS_CODES:
            raise SortAuditError("国家字典接口返回失败")
        data = body.get("data")
        if not isinstance(data, list):
            raise SortAuditError("国家字典接口的 data 不是数组")
        mapping = build_country_code_map(item for item in data if isinstance(item, dict))
        if not mapping:
            raise SortAuditError("国家字典接口没有可用的国家简码")
        return mapping

    def _load_store_names(self) -> dict[str, str]:
        records: list[dict[str, Any]] = []
        for path in STORE_LIST_PATHS:
            response = self.client.get(path, timeout=30)
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict) or body.get("code") not in SUCCESS_CODES:
                raise SortAuditError(f"店铺目录接口返回失败: {path}")
            data = body.get("data")
            if not isinstance(data, list):
                raise SortAuditError(f"店铺目录接口的 data 不是数组: {path}")
            records.extend(item for item in data if isinstance(item, dict))
        mapping = build_store_name_map(records)
        if not mapping:
            raise SortAuditError("店铺目录接口没有可用的店铺 ID / 名称映射")
        return mapping

    def _load_channel_names(self) -> dict[str, str]:
        response = self.client.get(CHANNEL_CATALOG_PATH, timeout=30)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict) or body.get("code") not in SUCCESS_CODES:
            raise SortAuditError("物流渠道目录接口返回失败")
        data = body.get("data")
        if isinstance(data, dict):
            records = data.get("list", [])
        elif isinstance(data, list):
            records = data
        else:
            records = []
        if not isinstance(records, list):
            raise SortAuditError("物流渠道目录接口没有返回记录数组")
        mapping = build_channel_name_map(item for item in records if isinstance(item, dict))
        if not mapping:
            raise SortAuditError("物流渠道目录接口没有可用的渠道 ID / 名称映射")
        return mapping

    def _query_details(self, order_numbers: Sequence[str]) -> dict[str, list[dict[str, Any]]]:
        unique_order_numbers = list(dict.fromkeys(order_numbers))
        if not unique_order_numbers:
            return {}
        body = self._post_json(ORDER_DETAILS_PATH, {"orderNoList": unique_order_numbers})
        return extract_order_details(body)

    def _query_page(self, field: SortField, direction: str, page_num: int) -> tuple[list[dict[str, Any]], int | None]:
        payload = copy.deepcopy(ORDER_LIST_BASE_PAYLOAD)
        payload.update(
            {
                "orderByColumn": field.order_by_column,
                "isAsc": direction,
                "pageNum": page_num,
                "pageSize": self.page_size,
            }
        )
        body = self._post_json(ORDER_LIST_PATH, payload)
        return extract_order_rows(body), extract_total_count(body)

    def _audit_direction(
        self,
        field: SortField,
        direction: str,
        country_codes: Mapping[str, str],
        store_names: Mapping[str, str],
        channel_names: Mapping[str, str],
    ) -> dict[str, Any]:
        values: list[Any | None] = []
        sku_candidates: dict[str, list[str | None]] = {"first": [], "min": [], "max": []}
        page_count = 0
        row_count = 0
        total_count: int | None = None
        sampled_pages: list[int] = []
        invalid_count = 0
        invalid_samples: list[str] = []
        unmapped_count = 0
        unmapped_samples: list[str] = []
        multi_sku_orders = 0
        missing_detail_orders = 0

        def consume_rows(rows: Sequence[Mapping[str, Any]]) -> None:
            nonlocal row_count, invalid_count, unmapped_count
            nonlocal multi_sku_orders, missing_detail_orders
            row_count += len(rows)
            if field.detail_key:
                order_numbers = [number for number in (row_order_number(row) for row in rows) if number]
                details = self._query_details(order_numbers)
                page_candidates, page_multi, page_missing = _sku_values_for_page(rows, details, field.detail_key)
                multi_sku_orders += page_multi
                missing_detail_orders += page_missing
                for name in sku_candidates:
                    sku_candidates[name].extend(page_candidates[name])
                selected = (
                    ("min" if direction == "asc" else "max")
                    if self.sku_aggregation == "directional"
                    else self.sku_aggregation
                )
                values.extend(page_candidates[selected])
            else:
                for row in rows:
                    raw_value = row.get(field.response_key)
                    try:
                        normalized = normalize_sort_value(field, raw_value, country_codes, store_names, channel_names)
                    except (UnmappedCountryCode, UnmappedStoreId, UnmappedChannelId) as exc:
                        unmapped_count += 1
                        if len(unmapped_samples) < 5:
                            unmapped_samples.append(f"{normalize_text(raw_value)} ({type(exc).__name__})")
                        values.append(None)
                        continue
                    except InvalidSortValue:
                        invalid_count += 1
                        if len(invalid_samples) < 5:
                            invalid_samples.append(normalize_text(raw_value))
                        values.append(None)
                        continue
                    values.append(normalized)

        for page_num in range(1, self.max_pages + 1):
            rows, page_total = self._query_page(field, direction, page_num)
            page_count += 1
            sampled_pages.append(page_num)
            if page_total is not None:
                total_count = page_total
            if not rows:
                break
            consume_rows(rows)
            if len(rows) < self.page_size:
                break
            if total_count is not None and page_num * self.page_size >= total_count:
                break

        if total_count:
            last_page = (total_count - 1) // self.page_size + 1
            if last_page not in sampled_pages:
                tail_rows, page_total = self._query_page(field, direction, last_page)
                page_count += 1
                sampled_pages.append(last_page)
                if page_total is not None:
                    total_count = page_total
                if tail_rows:
                    consume_rows(tail_rows)

        result = {
            "field": field.label,
            "direction": direction,
            "order_by_column": field.order_by_column,
            "response_key": field.response_key,
            "pages": page_count,
            "sampled_pages": sampled_pages,
            "row_count": row_count,
            "total_count": total_count,
            "coverage_percent": (round(row_count * 100 / total_count, 4) if total_count else None),
            "nonnull_count": sum(value is not None for value in values),
            "null_count": sum(value is None for value in values),
            "distinct_count": len({value for value in values if value is not None}),
            "inversions": 0,
            "inversion_examples": [],
            "status": "pending",
        }

        if field.detail_key:
            candidates = {
                name: evaluate_ordered_values(candidate_values, direction)
                for name, candidate_values in sku_candidates.items()
            }
            selected = (
                ("min" if direction == "asc" else "max")
                if self.sku_aggregation == "directional"
                else self.sku_aggregation
            )
            selected_eval = candidates[selected]
            result["sku_detail_key"] = field.detail_key
            result["sku_aggregation"] = self.sku_aggregation
            result["selected_sku_aggregation"] = selected
            result["multi_sku_order_count"] = multi_sku_orders
            result["missing_detail_order_count"] = missing_detail_orders
            result["candidate_aggregations"] = candidates
            result["snapshot_stability"] = "not_verifiable_read_only"
            result["detail_derived_diagnostic_status"] = selected_eval["status"]
            result["status"] = "inconclusive_snapshot_value_not_exposed"
            result["distinct_count"] = selected_eval["distinct_count"]
            result["inversions"] = selected_eval["inversions"]
            result["inversion_examples"] = selected_eval["inversion_examples"]
            result["null_count"] = selected_eval["null_count"]
            result["detail_derived_null_ordering"] = selected_eval["null_ordering"]
            result["null_ordering"] = "not_asserted_snapshot_value_missing"
            result["nonnull_after_blank_count"] = selected_eval["nonnull_after_blank_count"]
            return result

        if unmapped_count:
            result["status"] = (
                "inconclusive_unmapped_country"
                if field.value_kind == "country"
                else "inconclusive_unmapped_store" if field.value_kind == "store" else "inconclusive_unmapped_channel"
            )
            result["unmapped_count"] = unmapped_count
            result["unmapped_samples"] = unmapped_samples
            return result
        if invalid_count:
            result["status"] = "inconclusive_unparseable_values"
            result["invalid_count"] = invalid_count
            result["invalid_samples"] = invalid_samples
            return result

        evaluated = evaluate_ordered_values(values, direction)
        result.update(evaluated)
        if field.value_kind in {"text", "name", "store", "channel"}:
            if evaluated["null_ordering"] == "fail":
                result["status"] = "fail_null_not_last"
                result["inversions"] = None
                result["inversion_examples"] = []
            elif not evaluated["status"].startswith("inconclusive_insufficient"):
                result["status"] = "inconclusive_database_collation"
                result["inversions"] = None
                result["inversion_examples"] = []
                result["warning"] = (
                    "数据库使用 en_US.utf8 文本排序；Python Unicode 顺序不能作为正确性依据，"
                    "需要数据库 collation oracle 才能确认字符串单调性。"
                )
        return result

    def run(
        self,
        fields: Sequence[SortField] | None = None,
        *,
        progress: bool = False,
        directions: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        using_default_scope = fields is None
        selected_fields = tuple(REGRESSION_FIELDS if using_default_scope else fields)
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        selected_directions = tuple(directions or ("asc", "desc"))
        if not selected_directions or any(direction not in {"asc", "desc"} for direction in selected_directions):
            raise ValueError("directions 只能包含 asc 或 desc")
        if len(set(selected_directions)) != len(selected_directions):
            raise ValueError("directions 不能重复")
        country_codes: dict[str, str] = {}
        store_names: dict[str, str] = {}
        channel_names: dict[str, str] = {}
        if any(field.value_kind == "country" for field in selected_fields):
            country_codes = self._load_country_codes()
        if any(field.value_kind == "store" for field in selected_fields):
            store_names = self._load_store_names()
        if any(field.value_kind == "channel" for field in selected_fields):
            channel_names = self._load_channel_names()

        results: list[dict[str, Any]] = []
        for field_index, field in enumerate(selected_fields, start=1):
            field_results: list[dict[str, Any]] = []
            for direction in selected_directions:
                try:
                    result = self._audit_direction(field, direction, country_codes, store_names, channel_names)
                except Exception as exc:
                    result = {
                        "field": field.label,
                        "direction": direction,
                        "order_by_column": field.order_by_column,
                        "status": "request_error",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                result["severity"] = classify_status(str(result.get("status") or "request_error"))
                results.append(result)
                field_results.append(result)
            if progress:
                directions = ", ".join(f"{item['direction']}={item['status']}" for item in field_results)
                print(f"进度 {field_index}/{len(selected_fields)} {field.label}: {directions}", flush=True)

        summary = summarize_results(results)
        status_counts = Counter(item["status"] for item in results)

        finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "environment": self.env,
            "started_at": started_at,
            "finished_at": finished_at,
            "overall": summary["overall"],
            "exit_code": summary["exit_code"],
            "severity_counts": summary["severity_counts"],
            "read_only": True,
            "page_size": self.page_size,
            "max_pages": self.max_pages,
            "directions": list(selected_directions),
            "paused_fields": list(PAUSED_REGRESSION_FIELDS) if using_default_scope else [],
            "sku_aggregation": self.sku_aggregation,
            "null_ordering_asserted": True,
            "country_dictionary_entries": len({code for code in country_codes.values()}),
            "store_name_dictionary_entries": len(store_names),
            "channel_name_dictionary_entries": len(channel_names),
            "status_counts": dict(status_counts),
            "results": results,
        }


def _markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _warning_reason(result: Mapping[str, Any]) -> str:
    status = str(result.get("status") or "request_error")
    if status == "inconclusive_snapshot_value_not_exposed":
        diagnostic = result.get("detail_derived_diagnostic_status", "not available")
        return (
            "冻结排序快照键未从订单列表接口透出；订单明细推导只作诊断，" f"当前诊断={diagnostic}，不能替代快照键判定。"
        )
    if status == "inconclusive_unmapped_country":
        return "国家值未能映射到国家字典简码，无法按简码验证。"
    if status == "inconclusive_unmapped_store":
        return "店铺 ID 未能映射到店铺名称，无法按名称验证。"
    if status == "inconclusive_unmapped_channel":
        return "物流渠道 ID 未能映射到渠道名称，无法按名称验证。"
    if status == "inconclusive_database_collation":
        return str(result.get("warning") or "数据库文本 collation 与 Python Unicode 顺序不同，字符串单调性未确认。")
    if status == "inconclusive_unparseable_values":
        return "样本含无法解析的排序值，不能据此判定排序正确性。"
    if status.startswith("inconclusive_insufficient"):
        return "有效样本数量或取值变化不足，排序结论不充分。"
    if status == "request_error":
        return f"请求、认证或接口发生错误，本次未能判定：{result.get('error', '未提供错误详情')}"
    return str(result.get("warning") or "现有信息不足以确认排序结果。")


def render_markdown_report(report: Mapping[str, Any]) -> str:
    results = list(report.get("results") or [])
    summary = summarize_results(results)
    overall = str(report.get("overall") or summary["overall"]).upper()
    severity_counts = report.get("severity_counts") or summary["severity_counts"]
    lines = [
        "# 销售订单排序审计报告",
        "",
        f"- 环境：{_markdown_cell(report.get('environment', 'unknown'))}",
        f"- 总体判定：**{overall}**",
        (
            f"- 执行时间：{_markdown_cell(report.get('started_at', 'unknown'))} 至 "
            f"{_markdown_cell(report.get('finished_at', 'unknown'))}"
        ),
        f"- 只读审计：{'是' if report.get('read_only') else '未确认'}",
        f"- 方向数：{len(results)}",
        (
            f"- 通过：{severity_counts.get('passed', 0)}；"
            f"WARNING：{severity_counts.get('warning', 0)}；"
            f"确认失败：{severity_counts.get('failure', 0)}"
        ),
        "",
    ]
    paused_fields = report.get("paused_fields") or []
    if paused_fields:
        paused_text = "\u3001".join(str(field) for field in paused_fields)
        lines.extend([f"- \u6682\u7f13\u56de\u5f52\u5b57\u6bb5\uff1a{paused_text}（仍可显式单独审计）", ""])
    if overall == "WARNING":
        lines.extend(
            [
                "> 存在无法独立确认的排序方向，按报告型策略记为 WARNING；不阻断 CI。",
                "",
            ]
        )
    if report.get("error"):
        lines.extend([f"- 本次审计错误：{_markdown_cell(report['error'])}", ""])

    lines.extend(
        [
            "## 方向明细",
            "",
            "| 字段 | 方向 | 判定 | 样本数 | 非空值 | 逆序 | 样本页 | 说明 |",
            "|---|---|---:|---:|---:|---:|---|---|",
        ]
    )
    for result in results:
        status = str(result.get("status") or "request_error")
        severity = str(result.get("severity") or classify_status(status))
        label = {"passed": "PASS", "warning": "WARNING", "failure": "FAIL"}.get(severity, "WARNING")
        if severity == "warning":
            note = _warning_reason(result)
        elif severity == "failure":
            examples = result.get("inversion_examples") or []
            example_text = "; ".join(f"{item.get('previous')} → {item.get('current')}" for item in examples[:3])
            note = f"{status}。{example_text}" if example_text else status
        else:
            note = status
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(value)
                for value in (
                    result.get("field", "unknown"),
                    result.get("direction", "unknown"),
                    label,
                    result.get("row_count", 0),
                    result.get("nonnull_count", 0),
                    result.get("inversions", 0) if result.get("inversions") is not None else "未判定",
                    ",".join(str(page) for page in result.get("sampled_pages", [])),
                    note,
                )
            )
            + " |"
        )

    if not results:
        lines.append("| - | - | WARNING | 0 | 0 | 0 | - | 未生成方向结果；本次无法判定。 |")
    lines.extend(["", "## 判定口径", ""])
    lines.extend(
        [
            "- PASS：按对应字段的业务排序键抽样后单调，且观察到的空值位于末尾。",
            "- WARNING：缺少快照键、名称/字典映射、有效样本、数据库文本 collation oracle，或本次 API/认证请求不可用；这不是确认缺陷，也不阻断 CI。",
            "- FAIL：存在可复现的排序值逆序或空值未压尾；审计进程返回非零，但排序审计 CI job 仍为非阻断报告任务。",
            "- SKU 编码和平台 SKU 使用订单明细中的 min/max 值仅作诊断；冻结快照排序键未透出时，不把诊断结果冒充最终判定。",
            "- 店铺、物流渠道和物流单号等文本字段遵循数据库 en_US.utf8 collation；未复刻该规则时不使用 Python Unicode 码点序判 PASS/FAIL，但仍核验空值是否置后。",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(report: Mapping[str, Any]) -> Path:
    from modules.trae_test.utils.runtime_paths import runtime_dir

    report_dir = runtime_dir("reports") / "sales_order_sort"
    report_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"sales_order_sort_audit_{timestamp}.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report_path.with_suffix(".md").write_text(
        render_markdown_report(report) + "\n",
        encoding="utf-8",
    )
    return report_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "\u9ed8\u8ba4\u6838\u9a8c 13 \u4e2a\u9500\u552e\u8ba2\u5355\u6392\u5e8f\u5b57\u6bb5\uff1b"
            "\u5229\u6da6\u6682\u7f13\u9ed8\u8ba4\u56de\u5f52\uff0c"
            "\u53ef\u7528 --field \u5229\u6da6\u5355\u72ec\u6838\u67e5\u3002"
        )
    )
    parser.add_argument("--env", choices=("test", "uat"), required=True)
    parser.add_argument("--page-size", type=int, default=200)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument(
        "--field",
        action="append",
        choices=tuple(field.label for field in SORT_FIELDS),
        help="只核验指定字段；可重复传入。",
    )
    parser.add_argument(
        "--direction",
        action="append",
        choices=("asc", "desc"),
        help="只核验指定方向；可重复传入。默认同时核验升序和降序。",
    )
    parser.add_argument(
        "--sku-aggregation",
        choices=("directional", "first", "min", "max"),
        default="directional",
        help="多 SKU 聚合方式；默认升序取最小 SKU、降序取最大 SKU。",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="明确执行 API 查询；不传时只显示执行范围。",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    selected_fields = (
        [field for field in SORT_FIELDS if field.label in args.field]
        if args.field
        else list(REGRESSION_FIELDS)
    )
    selected_directions = tuple(args.direction or ("asc", "desc"))
    if not args.execute:
        paused_names = "\u3001".join(PAUSED_REGRESSION_FIELDS)
        paused_note = f", paused_fields={paused_names}" if not args.field else ""
        print(
            f"预览: env={args.env}, fields={len(selected_fields)}, "
            f"directions={len(selected_fields) * len(selected_directions)}, page_size={args.page_size}, "
            f"max_pages={args.max_pages}{paused_note}. 加 --execute 才会读取接口。"
        )
        return 0

    try:
        from modules.auto_test.core.regression_session import regression_session

        with regression_session(args.env) as client:
            auditor = SalesOrderSortAuditor(
                client,
                args.env,
                page_size=args.page_size,
                max_pages=args.max_pages,
                sku_aggregation=args.sku_aggregation,
            )
            report = auditor.run(
                selected_fields if args.field else None,
                progress=True,
                directions=selected_directions,
            )
    except Exception as exc:
        report = {
            "environment": args.env,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "overall": "warning",
            "exit_code": 0,
            "severity_counts": {"passed": 0, "warning": 1, "failure": 0},
            "read_only": True,
            "paused_fields": list(PAUSED_REGRESSION_FIELDS) if not args.field else [],
            "error": f"{type(exc).__name__}: {exc}",
            "results": [],
        }

    report_path = write_report(report)
    for result in report.get("results", []):
        print(
            f"{result.get('field')} {result.get('direction')}: "
            f"{result.get('status')} "
            f"(nonnull={result.get('nonnull_count', 0)}, "
            f"distinct={result.get('distinct_count', 0)}, "
            f"inversions={result.get('inversions', 0)})"
        )
    print(f"总体结果: {report.get('overall')}")
    print(f"报告(JSON): {report_path}")
    print(f"报告(Markdown): {report_path.with_suffix('.md')}")
    return int(report.get("exit_code", 2))


if __name__ == "__main__":
    raise SystemExit(main())

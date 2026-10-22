"""Read-only regression of sales-order delivery status filters (requirement 1003062)."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from modules.auto_test.core.regression_session import regression_session
from modules.trae_test.utils.runtime_paths import runtime_dir


ORDER_LIST_PATH = "/oms-admin/sales/order/batchListNew"
STATUS_FLAGS = (
    ("未交运", "0"),
    ("交运中", "10"),
    ("交运失败", "30"),
    ("交运成功", "20"),
)
SUCCESS_CODES = {0, "0", 200, "200"}
VALID_STATUSES = {"0", "10", "20", "30"}

# The query fields other than the delivery filter mirror the request supplied
# for this regression. No order is created, updated, or deleted.
BASE_PAYLOAD: dict[str, Any] = {
    "displayName": "",
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
    "salesOrderQueryClassDto": "",
    "transNo": "",
    "trackingNumber": "",
    "logisticsTransferNo": "",
    "dotTrackingNo": "",
    "remark": "",
    "sendMessage": "",
    "recipientName": "",
    "recipientEmail": "",
    "recipientAddress": "",
    "itemId": "",
    "sellerSku": "",
    "groupSkuId": "",
    "pageNum": 1,
    "pageSize": 500,
    "orderStatus": "0",
    "storeIds": "",
    "providerChannelIds": "",
    "itemAttribute": "",
    "exceptionClassIds": "",
    "customerPanelExceptionClassIds": "",
    "customClassIds": "",
    "countryCode": "",
    "onlyShowMyProcessing": "0",
    "queryType": "0",
    "queryNotEmptyField": "orderId",
}


class ResponseShapeError(ValueError):
    """The response cannot be used as evidence for delivery status filtering."""


class BusinessResponseError(ResponseShapeError):
    """The order-list endpoint returned a non-success business code."""

    def __init__(self, code: Any):
        super().__init__(f"business response code is {code!r}")
        self.code = code


def build_payload(flag: str, page_num: int, page_size: int) -> dict[str, Any]:
    if flag not in VALID_STATUSES:
        raise ValueError(f"Unsupported delivery status: {flag}")
    if page_num < 1 or page_size < 1:
        raise ValueError("page_num and page_size must be positive")
    fixed_filter = [{"selectType": "47", "selectFlag": flag}]
    payload = dict(BASE_PAYLOAD)
    payload["fixedClassId"] = fixed_filter
    payload["salesOrderQueryClassDto"] = quote(
        json.dumps(fixed_filter, ensure_ascii=False, separators=(",", ":")), safe=""
    )
    payload["pageNum"] = page_num
    payload["pageSize"] = page_size
    return payload


def extract_page(body: Mapping[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    data = body.get("data")
    if not isinstance(data, dict):
        raise ResponseShapeError("response.data is not an object")
    table = data.get("tableDataInfo")
    containers = [table, data] if isinstance(table, dict) else [data]
    for container in containers:
        for key in ("list", "rows", "records", "orders", "data"):
            if key not in container:
                continue
            rows = container[key]
            total_raw = container.get("total", data.get("total"))
            if rows is None and str(total_raw) == "0":
                rows = []
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise ResponseShapeError(f"response {key} is not an order array")
            if total_raw is None:
                return rows, None
            try:
                total = int(total_raw)
            except (TypeError, ValueError) as exc:
                raise ResponseShapeError("response total is not an integer") from exc
            if total < 0:
                raise ResponseShapeError("response total is negative")
            return rows, total
    raise ResponseShapeError("response has no recognized order array")


def status_value(row: Mapping[str, Any]) -> str | None:
    value = row.get("deliveryStatus")
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return value.strip() or None
    return None


def order_identity(row: Mapping[str, Any]) -> str | None:
    # TEST list rows can share orderId; orderNo distinguishes the returned orders.
    value = row.get("orderNo")
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, str)):
        return str(value).strip() or None
    return None


def inspect_rows(rows: Sequence[Mapping[str, Any]], expected_flag: str) -> dict[str, Any]:
    observed = Counter()
    missing = 0
    for row in rows:
        value = status_value(row)
        if value is None:
            missing += 1
        else:
            observed[value] += 1
    return {
        "row_count": len(rows),
        "missing_status_count": missing,
        "observed_status_counts": dict(sorted(observed.items())),
        "mismatch_count": sum(count for status, count in observed.items() if status != expected_flag),
    }


def query_status(client: Any, label: str, flag: str, page_size: int, max_pages: int) -> dict[str, Any]:
    count = 0
    missing = 0
    mismatch = 0
    observed: Counter[str] = Counter()
    page_count = 0
    total: int | None = None
    complete = False
    error: Exception | None = None
    seen_order_numbers: set[str] = set()
    duplicate_order_count = 0
    missing_order_no_count = 0
    for page_num in range(1, max_pages + 1):
        try:
            response = client.post(
                ORDER_LIST_PATH,
                json=build_payload(flag, page_num, page_size),
                timeout=90,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ResponseShapeError("response is not a JSON object")
            code = body.get("code")
            if code not in SUCCESS_CODES:
                raise BusinessResponseError(code)
            rows, page_total = extract_page(body)
        except Exception as exc:
            error = exc
            break
        page_count += 1
        if page_total is not None:
            total = page_total
        inspected = inspect_rows(rows, flag)
        count += inspected["row_count"]
        missing += inspected["missing_status_count"]
        mismatch += inspected["mismatch_count"]
        observed.update(inspected["observed_status_counts"])
        for row in rows:
            order_no = order_identity(row)
            if order_no is None:
                missing_order_no_count += 1
            elif order_no in seen_order_numbers:
                duplicate_order_count += 1
            else:
                seen_order_numbers.add(order_no)
        if total is not None:
            if count >= total:
                complete = True
                break
            if not rows:
                break
        elif not rows or len(rows) < page_size:
            complete = True
            break

    # Counting the same order twice cannot establish that every result was checked.
    if duplicate_order_count or (page_count > 1 and missing_order_no_count):
        complete = False
    if mismatch:
        status = "FAIL"
    elif isinstance(error, BusinessResponseError) and error.code not in (401, "401", 403, "403"):
        status = "FAIL"
    elif error is not None:
        status = "BLOCKED"
    elif missing:
        status = "BLOCKED"
    elif count == 0:
        if complete and total in (None, 0):
            # Delivery in progress is transient. A complete empty result is
            # valid; the three stable states still require rows as evidence.
            status = "EMPTY_OK" if flag == "10" else "NO_SAMPLE"
        else:
            status = "BLOCKED"
    elif not complete:
        status = "PARTIAL"
    else:
        status = "PASS"
    result = {
        "label": label,
        "select_type": "47",
        "select_flag": flag,
        "status": status,
        "pages_checked": page_count,
        "rows_checked": count,
        "reported_total": total,
        "complete": complete,
        "missing_status_count": missing,
        "mismatch_count": mismatch,
        "duplicate_order_count": duplicate_order_count,
        "missing_order_no_count": missing_order_no_count,
        "observed_status_counts": dict(sorted(observed.items())),
        "row_status_verified": count > 0 and missing == 0 and mismatch == 0,
    }
    if error is not None:
        result["failed_page"] = page_count + 1
        result["error_type"] = type(error).__name__
        result["error"] = str(error)[:300]
    return result


def report_path() -> Path:
    directory = runtime_dir("reports") / "sales_order_delivery_status"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return directory / f"req1003062_delivery_status_{stamp}.json"


def run(env: str, page_size: int, max_pages: int, flags: Sequence[str] | None = None) -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results: list[dict[str, Any]] = []
    selected = [(label, flag) for label, flag in STATUS_FLAGS if flags is None or flag in flags]
    try:
        with regression_session(env) as client:
            for label, flag in selected:
                try:
                    result = query_status(client, label, flag, page_size, max_pages)
                except Exception as exc:
                    result = {
                        "label": label,
                        "select_type": "47",
                        "select_flag": flag,
                        "status": "BLOCKED",
                        "error_type": type(exc).__name__,
                        "error": str(exc)[:300],
                    }
                results.append(result)
                print(
                    f"{label}({flag}): {result['status']}, "
                    f"rows={result.get('rows_checked', 0)}, "
                    f"mismatch={result.get('mismatch_count', 0)}",
                    flush=True,
                )
    except Exception as exc:
        results = [
            {
                "label": label,
                "select_type": "47",
                "select_flag": flag,
                "status": "BLOCKED",
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            }
            for label, flag in selected
        ]
    statuses = {result["status"] for result in results}
    overall = (
        "FAIL" if "FAIL" in statuses else "INCOMPLETE" if statuses & {"BLOCKED", "PARTIAL", "NO_SAMPLE"} else "PASS"
    )
    return {
        "requirement_id": "1003062",
        "environment": env,
        "endpoint": ORDER_LIST_PATH,
        "read_only": True,
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "page_size": page_size,
        "max_pages": max_pages,
        "overall": overall,
        "results": results,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only sales-order delivery-status filter regression")
    parser.add_argument("--env", choices=("test", "uat"), default="test")
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--flags", default="0,10,30,20", help="Comma-separated status flags to check")
    parser.add_argument("--execute", action="store_true", help="Send read-only order-list requests")
    args = parser.parse_args(argv)
    if not 1 <= args.page_size <= 500:
        parser.error("--page-size must be between 1 and 500")
    if not 1 <= args.max_pages <= 1000:
        parser.error("--max-pages must be between 1 and 1000")
    flags = args.flags.split(",")
    if not flags or len(set(flags)) != len(flags) or any(flag not in VALID_STATUSES for flag in flags):
        parser.error("--flags must be a unique comma-separated subset of 0,10,30,20")
    if not args.execute:
        print(
            f"Preview: env={args.env}, endpoint={ORDER_LIST_PATH}, "
            f"flags={flags}, "
            f"page_size={args.page_size}, max_pages={args.max_pages}"
        )
        return 0
    report = run(args.env, args.page_size, args.max_pages, flags)
    path = report_path()
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Overall: {report['overall']}")
    print(f"Report: {path}")
    return 1 if report["overall"] == "FAIL" else 2 if report["overall"] == "INCOMPLETE" else 0


if __name__ == "__main__":
    raise SystemExit(main())

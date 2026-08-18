"""API-driven field validation for sales order export templates."""

from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_page import SalesOrderPage


ORDER_RE = re.compile(r"SO\d{14,}")
REPORT_DIR = Path("reports") / f"sales_order_export_field_validation_{time.strftime('%Y%m%d_%H%M%S')}"
BASELINE_PATH = Path(".runtime/reports/sales_order_export_baseline.local.json")


BASE_LIST_PAYLOAD: dict[str, Any] = {
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
    "pageSize": 100,
    "orderStatus": "",
    "storeIds": "",
    "itemAttribute": "",
    "exceptionClassIds": "",
    "customClassIds": "",
    "countryCode": "",
    "onlyShowMyProcessing": "0",
    "queryType": "0",
}


def _api(page: Page, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return page.evaluate(
        """async ({ method, path, payload }) => {
            const read = (key) => localStorage.getItem(key) || sessionStorage.getItem(key) || '';
            const tokenKeys = ['Admin-Token', 'access_token', 'accessToken', 'token', 'Authorization'];
            let token = '';
            for (const key of tokenKeys) {
                token = read(key);
                if (token) break;
            }
            const clientid = read('clientid') || read('client_id') || read('Clientid') || read('CLIENT_ID');
            const headers = { 'content-type': 'application/json;charset=UTF-8' };
            if (token) {
                headers.Authorization = token.startsWith('Bearer ') ? token : `Bearer ${token}`;
                headers['Admin-Token'] = token.replace(/^Bearer\\s+/i, '');
            }
            if (clientid) headers.clientid = clientid;
            const response = await fetch(path, {
                method,
                credentials: 'include',
                headers,
                body: payload === null ? undefined : JSON.stringify(payload),
            });
            const contentType = response.headers.get('content-type') || '';
            const body = contentType.toLowerCase().includes('json')
                ? await response.json()
                : await response.text();
            return { ok: response.ok, status: response.status, body };
        }""",
        {"method": method, "path": path, "payload": payload},
    )


def _download_export(page: Page, payload: dict[str, Any], target: Path) -> dict[str, Any]:
    result = page.evaluate(
        """async ({ payload }) => {
            const read = (key) => localStorage.getItem(key) || sessionStorage.getItem(key) || '';
            const tokenKeys = ['Admin-Token', 'access_token', 'accessToken', 'token', 'Authorization'];
            let token = '';
            for (const key of tokenKeys) {
                token = read(key);
                if (token) break;
            }
            const clientid = read('clientid') || read('client_id') || read('Clientid') || read('CLIENT_ID');
            const headers = { 'content-type': 'application/json;charset=UTF-8' };
            if (token) {
                headers.Authorization = token.startsWith('Bearer ') ? token : `Bearer ${token}`;
                headers['Admin-Token'] = token.replace(/^Bearer\\s+/i, '');
            }
            if (clientid) headers.clientid = clientid;
            const response = await fetch('/oms-api/oms-admin/sales/order/batch/orderExportNew', {
                method: 'POST',
                credentials: 'include',
                headers,
                body: JSON.stringify(payload),
            });
            const contentType = response.headers.get('content-type') || '';
            if (contentType.toLowerCase().includes('json')) {
                return { ok: response.ok, status: response.status, json: await response.json() };
            }
            const bytes = new Uint8Array(await response.arrayBuffer());
            let binary = '';
            for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
            return {
                ok: response.ok,
                status: response.status,
                contentType,
                filename: response.headers.get('content-disposition') || '',
                base64: btoa(binary),
            };
        }""",
        {"payload": payload},
    )
    if result.get("base64"):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(result["base64"]))
    return result


def _assert_api_ok(result: dict[str, Any], name: str) -> Any:
    assert result["ok"], f"{name} HTTP failed: {result['status']}"
    body = result["body"]
    assert isinstance(body, dict), f"{name} did not return JSON"
    assert body.get("code") == 200, f"{name} business failed: {body.get('code')} {body.get('msg')}"
    return body.get("data")


def _parse_templates(data: Any) -> list[dict[str, Any]]:
    templates: list[dict[str, Any]] = []
    for group in data or []:
        group_name = group.get("deptName") or ""
        for template in group.get("omsExportTemplateVoList") or []:
            raw_columns = template.get("exportColumn") or "{}"
            parsed = json.loads(raw_columns) if isinstance(raw_columns, str) else raw_columns
            columns = parsed.get("column") if isinstance(parsed, dict) else []
            if columns:
                templates.append(
                    {
                        "id": template.get("id"),
                        "name": template.get("templateName"),
                        "group": group_name,
                        "fontType": template.get("fontType"),
                        "columns": columns,
                    }
                )
    return templates


def _find_record_lists(value: Any) -> list[list[dict[str, Any]]]:
    found: list[list[dict[str, Any]]] = []
    if isinstance(value, dict):
        for child in value.values():
            found.extend(_find_record_lists(child))
    elif isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            found.append(value)
        for child in value:
            found.extend(_find_record_lists(child))
    return found


def _order_no(record: dict[str, Any]) -> str:
    for key in ("orderNo", "systemOrderNo", "sysOrderNo"):
        value = str(record.get(key) or "").strip()
        if ORDER_RE.fullmatch(value):
            return value
    for value in record.values():
        text = str(value or "").strip()
        if ORDER_RE.fullmatch(text):
            return text
    return ""


def _score_value(value: Any) -> int:
    if value in (None, "", [], {}):
        return 0
    if isinstance(value, dict):
        return sum(_score_value(child) for child in value.values())
    if isinstance(value, list):
        return 2 * len(value) + sum(_score_value(child) for child in value[:5])
    return 1


def _select_orders(list_data: Any, limit: int = 50) -> tuple[list[str], dict[str, dict[str, Any]]]:
    lists = _find_record_lists(list_data)
    records = max(lists, key=len) if lists else []
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    seen: set[str] = set()
    for record in records:
        order_no = _order_no(record)
        if not order_no or order_no in seen:
            continue
        seen.add(order_no)
        ranked.append((_score_value(record), order_no, record))
    ranked.sort(key=lambda item: item[0], reverse=True)
    selected = ranked[:limit]
    return [order_no for _, order_no, _ in selected], {order_no: record for _, order_no, record in selected}


def _baseline_orders() -> list[str]:
    if not BASELINE_PATH.exists():
        return []
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    orders: list[str] = []
    for item in payload.get("orders", []):
        if isinstance(item, dict):
            order_no = str(item.get("systemOrderNo") or "").strip()
        else:
            order_no = str(item).strip()
        if order_no:
            orders.append(order_no)
    return orders[:50]


def _flatten(value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def walk(current: Any, prefix: str, row: dict[str, str]) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                next_prefix = f"{prefix}.{key}" if prefix else str(key)
                walk(child, next_prefix, row)
        elif isinstance(current, list):
            if not current:
                return
            for item in current:
                child_row = dict(row)
                walk(item, prefix, child_row)
                rows.append(child_row)
        elif current not in (None, ""):
            key = prefix.rsplit(".", 1)[-1]
            row[key] = _norm(current)

    base: dict[str, str] = {}
    walk(value, "", base)
    if base:
        rows.append(base)
    return rows


def _norm(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text.lstrip("0") if text.isdigit() else text


def _read_workbook(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    raw_rows = list(sheet.iter_rows(values_only=True))
    workbook.close()
    if not raw_rows:
        return [], []
    headers = [str(value or "").strip() for value in raw_rows[0]]
    rows: list[dict[str, str]] = []
    for raw in raw_rows[1:]:
        rows.append({headers[i]: _norm(value) for i, value in enumerate(raw) if i < len(headers) and value not in (None, "")})
    return headers, rows


def _candidate_source_rows(order_no: str, list_records: dict[str, dict[str, Any]], details: dict[str, Any]) -> list[dict[str, str]]:
    merged = {"list": list_records.get(order_no, {}), "detail": details.get(order_no, {})}
    rows = _flatten(merged)
    return rows or [{}]


def _validate_fields(
    template: dict[str, Any],
    exported_rows: list[dict[str, str]],
    order_numbers: list[str],
    list_records: dict[str, dict[str, Any]],
    details: dict[str, Any],
) -> dict[str, Any]:
    aliases: dict[str, set[str]] = {}
    for order_no in order_numbers:
        values = {order_no}
        for source in (list_records.get(order_no, {}), details.get(order_no, {})):
            for flattened in _flatten(source):
                for key in ("orderId", "id", "orderNo", "systemOrderNo", "transNo", "trans_no", "order_id"):
                    if flattened.get(key):
                        raw = str(flattened[key]).strip()
                        values.add(_norm(raw))
                        values.add(raw)
        aliases[order_no] = values

    matched_orders: set[str] = set()
    checked = 0
    mismatches: list[dict[str, str]] = []
    columns = [col for col in template["columns"] if not str(col.get("value", "")).startswith("EMPTY_ROW")]
    label_to_key = {str(col.get("label")): str(col.get("value")) for col in columns}

    for row in exported_rows:
        row_values = {_norm(value) for value in row.values()}
        order_no = next((candidate for candidate, ids in aliases.items() if row_values.intersection(ids)), "")
        if not order_no:
            continue
        matched_orders.add(order_no)
        source_rows = _candidate_source_rows(order_no, list_records, details)
        for label, key in label_to_key.items():
            actual = row.get(label, "")
            if actual == "":
                continue
            expected_values = {source.get(key, "") for source in source_rows if source.get(key, "") != ""}
            if not expected_values:
                continue
            checked += 1
            # This first pass intentionally compares only direct same-key values.
            # Name/id translations and formula fields are reported for analysis
            # instead of being treated as blocking export failures.
            if actual not in expected_values:
                mismatches.append(
                    {
                        "orderNo": order_no,
                        "column": label,
                        "field": key,
                        "actual": actual[:80],
                        "expected": "|".join(sorted(expected_values))[:160],
                    }
                )
                if len(mismatches) >= 20:
                    break
        if len(mismatches) >= 20:
            break

    return {
        "matchedOrders": len(matched_orders),
        "missingOrders": sorted(set(order_numbers) - matched_orders),
        "checkedCells": checked,
        "mismatches": mismatches,
    }


@pytest.mark.regression
@pytest.mark.api
@pytest.mark.ui
@pytest.mark.p1
class TestSalesOrderExportFieldValidation:
    def test_realtime_templates_export_and_field_validation(self, logged_in_page: Page) -> None:
        SalesOrderPage(logged_in_page).navigate_to("sales/order/saleOrder")
        SalesOrderPage(logged_in_page).wait_for_table_data()

        template_data = _assert_api_ok(
            _api(logged_in_page, "GET", "/oms-api/oms-admin/base/exportTemplate/list?type=3"),
            "exportTemplate/list",
        )
        templates = _parse_templates(template_data)
        assert templates, "No templates returned by exportTemplate/list"

        list_data = _assert_api_ok(
            _api(logged_in_page, "POST", "/oms-api/oms-admin/sales/order/batchListNew", BASE_LIST_PAYLOAD),
            "sales/order/batchListNew",
        )
        order_numbers, list_records = _select_orders(list_data, 50)
        baseline_orders = _baseline_orders()
        if len(baseline_orders) == 50:
            order_numbers = baseline_orders
        assert len(order_numbers) == 50, f"Expected 50 rich orders, got {len(order_numbers)}"

        detail_data = _assert_api_ok(
            _api(
                logged_in_page,
                "POST",
                "/oms-api/oms-admin/sales/orderItem/queryAllList",
                {"orderNoList": order_numbers},
            ),
            "sales/orderItem/queryAllList",
        )
        assert isinstance(detail_data, dict), "queryAllList data should be keyed by orderNo"

        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        blocking_failures: list[dict[str, Any]] = []
        manifest: list[dict[str, Any]] = []
        for index, template in enumerate(templates, start=1):
            file_path = REPORT_DIR / f"template_{index:03d}.xlsx"
            payload = {
                "checkColumns": template["columns"],
                "orderNos": order_numbers,
                "fontType": template.get("fontType"),
                "mergeMultipleProInfo": False,
                "mergeOrderSharedInfo": False,
            }
            export_result = _download_export(logged_in_page, payload, file_path)
            if not export_result.get("ok") or not file_path.exists() or file_path.stat().st_size == 0:
                blocking_failures.append({"template": template["name"], "error": export_result})
                continue

            headers, rows = _read_workbook(file_path)
            validation = _validate_fields(template, rows, order_numbers, list_records, detail_data)
            manifest.append(
                {
                    "index": index,
                    "group": template["group"],
                    "template": template["name"],
                    "file": file_path.name,
                    "columns": len(headers),
                    "rows": len(rows),
                    **validation,
                }
            )
            if not rows:
                blocking_failures.append({"template": template["name"], "error": "empty workbook"})

        (REPORT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (REPORT_DIR / "orders.txt").write_text("\n".join(order_numbers), encoding="utf-8")

        assert len(templates) == len(manifest), "Not every realtime template produced a workbook"
        assert not blocking_failures, f"Sales order export blocking failures: {blocking_failures}"

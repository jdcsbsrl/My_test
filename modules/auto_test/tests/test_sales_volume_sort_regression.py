"""Visible numeric sorting for the merged report."""

import json
import os
import time
from collections import Counter
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from modules.trae_test.utils.runtime_paths import runtime_dir

COLUMN_VALUES = """header => {
    const table=header.closest('.virtual-pro-table'), hr=header.getBoundingClientRect();
    const x=hr.left+hr.width/2;
    return Array.from(table.querySelectorAll('.virtual-pro-table__row')).filter(row => {
      const r=row.getBoundingClientRect(); return r.width>0 && r.height>0;
    }).map(row => {
      const cell=Array.from(row.querySelectorAll('.virtual-pro-table__cell')).find(c=>{
        const r=c.getBoundingClientRect(); return x>=r.left && x<=r.right;
      });
      const text=(cell?.innerText||'').trim().replaceAll(',','');
      return text === '' ? null : Number(text);
    }).filter(v=>v!==null && Number.isFinite(v));
}"""

REPORT_RESPONSE_TIMEOUT_MS = 90_000
REPORT_DOWNLOAD_TIMEOUT_MS = 90_000
SORT_RENDER_TIMEOUT_MS = 15_000


def _response_diagnostics(response):
    """Return safe response details for report API failures."""
    headers = response.headers
    content_type = headers.get("content-type", "")
    details = {
        "path": urlsplit(response.url).path,
        "status": response.status,
        "contentType": content_type,
        "contentLength": headers.get("content-length"),
    }
    if "json" in content_type.lower():
        try:
            body = response.json()
        except (TypeError, ValueError):
            body = {}
        for key in ("code", "msg", "message", "error"):
            value = body.get(key)
            if value not in (None, ""):
                details[key] = str(value)[:500]
    return details


def _request_diagnostics(request):
    details = {"path": urlsplit(request.url).path, "method": request.method}
    try:
        payload = request.post_data_json
    except (TypeError, ValueError):
        payload = None
    if isinstance(payload, dict):
        details["payloadKeys"] = sorted(payload)
        details["pageNum"] = payload.get("pageNum")
        details["pageSize"] = payload.get("pageSize")
        details["sortField"] = payload.get("sortField")
        details["sortOrder"] = payload.get("sortOrder")
        for key in ("payTimeBegin", "payTimeEnd", "sendDateBegin", "sendDateEnd"):
            if key in payload:
                details[key] = payload[key]
    return details


def _report_query_request(endpoint):
    return lambda request: endpoint in request.url and request.method == "POST"


def _wait_for_report_requests_idle(page, pending_requests, timeout_ms=REPORT_RESPONSE_TIMEOUT_MS):
    deadline = time.monotonic() + timeout_ms / 1000
    while pending_requests and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert not pending_requests, {
        "message": "Report query requests did not settle before the next UI action",
        "pendingPaths": [urlsplit(request.url).path for request in pending_requests],
    }


def _assert_report_rows(response, tab, action):
    details = _response_diagnostics(response)
    assert response.status == 200, {"tab": tab, "action": action, "response": details}
    try:
        body = response.json()
    except (TypeError, ValueError) as exc:
        raise AssertionError({"tab": tab, "action": action, "response": details}) from exc
    assert body.get("code") == 200, {"tab": tab, "action": action, "response": details}
    rows = body.get("rows")
    assert isinstance(rows, list) and rows, {
        "tab": tab,
        "action": action,
        "rowCount": len(rows) if isinstance(rows, list) else None,
        "response": details,
    }
    return rows


def _visible_numeric_values(page, header, timeout_ms=15_000):
    deadline = time.monotonic() + timeout_ms / 1000
    values = []
    while time.monotonic() < deadline:
        values = header.evaluate(COLUMN_VALUES)
        if len(values) >= 2:
            return values
        page.wait_for_timeout(250)
    return values


def _wait_for_sorted_numeric_values(page, header, arrow, descending, timeout_ms=15_000):
    deadline = time.monotonic() + timeout_ms / 1000
    values = []
    while time.monotonic() < deadline:
        values = header.evaluate(COLUMN_VALUES)
        active = "is-active" in (arrow.get_attribute("class") or "")
        if len(values) >= 2 and active and values == sorted(values, reverse=descending):
            return values
        page.wait_for_timeout(250)
    return values


def _download_report_export(page, menu_item, tab, label, direction):
    observed_responses = []

    def capture_report_response(response):
        if response.request.method == "POST" and "/sales/report/" in response.url:
            observed_responses.append(_response_diagnostics(response))

    page.on("response", capture_report_response)
    try:
        try:
            with page.expect_download(timeout=REPORT_DOWNLOAD_TIMEOUT_MS) as download_event:
                with page.expect_response(
                    lambda response: "/sales/report/" in response.url and response.request.method == "POST",
                    timeout=REPORT_RESPONSE_TIMEOUT_MS,
                ) as response_event:
                    menu_item.click()
                response = response_event.value
                details = _response_diagnostics(response)
                assert response.status == 200, {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "exportResponse": details,
                }
                assert "json" not in details["contentType"].lower(), {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "message": "Export endpoint returned JSON instead of a downloadable workbook",
                    "exportResponse": details,
                }
            return download_event.value, details, _request_diagnostics(response.request)
        except PlaywrightTimeoutError as exc:
            raise AssertionError(
                {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "message": "Export action did not produce a response and browser download within the limits",
                    "timeoutMs": {
                        "response": REPORT_RESPONSE_TIMEOUT_MS,
                        "download": REPORT_DOWNLOAD_TIMEOUT_MS,
                    },
                    "reportResponses": observed_responses[-5:],
                }
            ) from exc
    finally:
        page.remove_listener("response", capture_report_response)


def _open_report(page, ui_base_url):
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    page.wait_for_timeout(1500)
    page.get_by_text("SKU维度", exact=True).first.wait_for(state="visible", timeout=30000)


def _header(page, label):
    return page.locator(".virtual-pro-table__header-cell:visible").filter(has=page.get_by_text(label, exact=True)).last


def _sort_desc(page, label):
    header = _header(page, label)
    arrow = header.locator(".sort-caret.descending").first
    assert arrow.count(), label
    box = arrow.bounding_box()
    assert box
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(3000)
    return header


def test_sort_persists_across_pages(logged_in_page, ui_base_url, refresh_authenticated_http_client):
    refresh_authenticated_http_client()
    page = logged_in_page
    _open_report(page, ui_base_url)
    page.get_by_text("SKU维度", exact=True).click()
    with page.expect_response(
        lambda response: "queryOmsInventoryNew" in response.url and response.request.method == "POST",
        timeout=REPORT_RESPONSE_TIMEOUT_MS,
    ) as search_event:
        page.get_by_role("button", name="搜索", exact=True).click()
    _assert_report_rows(search_event.value, "SKU维度", "search")
    page.wait_for_timeout(3500)
    header = _sort_desc(page, "销量")
    first_page = header.evaluate(COLUMN_VALUES)
    assert len(first_page) >= 2, first_page
    assert first_page == sorted(first_page, reverse=True), first_page

    next_button = page.locator(".el-pagination .btn-next, .el-pagination button[aria-label='下一页']").first
    assert next_button.count(), "Pagination control missing"
    with page.expect_response(
        lambda response: "/sales/report/" in response.url and response.request.method == "POST", timeout=90000
    ) as captured:
        next_button.click()
    page.wait_for_timeout(3000)
    payload = json.loads(captured.value.request.post_data or "{}")
    assert payload.get("pageNum") == 2, payload
    assert payload.get("sortField") == "salesNumber" and payload.get("sortOrder") == "desc", payload
    second_page = _header(page, "销量").evaluate(COLUMN_VALUES)
    assert second_page, "Second page has no numeric rows"
    assert second_page == sorted(second_page, reverse=True), second_page
    assert max(second_page) <= min(first_page), {"page1": first_page, "page2": second_page}


def test_expand_keeps_active_sort(logged_in_page, ui_base_url, refresh_authenticated_http_client):
    refresh_authenticated_http_client()
    page = logged_in_page
    _open_report(page, ui_base_url)
    page.get_by_text("类目维度", exact=True).click()
    page.wait_for_timeout(800)
    with page.expect_response(
        lambda response: "queryCategorySalesDimensionReport" in response.url and response.request.method == "POST",
        timeout=REPORT_RESPONSE_TIMEOUT_MS,
    ) as search_event:
        page.get_by_role("button", name="搜索", exact=True).click()
    _assert_report_rows(search_event.value, "类目维度", "search")
    page.wait_for_timeout(4000)
    _sort_desc(page, "销量")
    rows = page.locator(".virtual-pro-table__row:visible")
    assert rows.count(), "No category rows to expand"
    expand = rows.first.locator("button.virtual-pro-table__expand").first
    assert expand.count(), "Expand control missing on category row"
    with page.expect_response(
        lambda response: "queryCategorySalesDimensionExpand" in response.url, timeout=90000
    ) as captured:
        expand.click()
    page.wait_for_timeout(3000)
    payload = json.loads(captured.value.request.post_data or "{}")
    assert payload.get("classIds"), payload
    assert payload.get("sortField") == "salesNumber" and payload.get("sortOrder") == "desc", payload
    expanded = page.locator("[class*='expand-row']:visible")
    assert expanded.count(), "Expanded detail rows did not render"


@pytest.mark.slow
def test_visible_numeric_sort_and_export(
    logged_in_page,
    ui_base_url,
    authenticated_http_client,
    api_base_url,
):
    page = logged_in_page
    latest_rows = {}
    latest_payloads = {}
    endpoints = {
        "SKU维度": "queryOmsInventoryNew",
        "店铺维度": "queryStoreSalesDimensionReport",
        "发货仓库维度": "queryWarehouseSalesDimensionReport",
        "国家维度": "queryCountrySalesDimensionReport",
        "类目维度": "queryCategorySalesDimensionReport",
    }

    pending_report_requests = set()
    report_request_history = []

    def track_report_request(request):
        if request.method == "POST" and "/sales/report/" in request.url:
            pending_report_requests.add(request)
            report_request_history.append(request)

    def complete_report_request(request):
        pending_report_requests.discard(request)

    page.on("request", track_report_request)
    page.on("requestfinished", complete_report_request)
    page.on("requestfailed", complete_report_request)
    tabs = ["SKU维度", "店铺维度", "发货仓库维度", "国家维度", "类目维度"]
    if os.environ.get("SALES_VOLUME_ROLE") == "procurement":
        tabs.remove("店铺维度")
    for tab in tabs:
        _open_report(page, ui_base_url)
        _wait_for_report_requests_idle(page, pending_report_requests)
        page.get_by_text(tab, exact=True).click()
        _wait_for_report_requests_idle(page, pending_report_requests)
        with page.expect_request(
            _report_query_request(endpoints[tab]), timeout=REPORT_RESPONSE_TIMEOUT_MS
        ) as search_request:
            page.get_by_role("button", name="搜索", exact=True).click()
        request = search_request.value
        response = request.response()
        assert response is not None, {
            "tab": tab,
            "action": "search",
            "requestPath": urlsplit(request.url).path,
            "failure": request.failure,
        }
        latest_rows[tab] = _assert_report_rows(response, tab, "search")
        latest_payloads[tab] = response.request.post_data_json or {}
        labels = ["销量", "日均销量", "库存(汇总)"]
        if tab != "SKU维度":
            labels.append("订单数")
        for label in labels:
            header = (
                page.locator(".virtual-pro-table__header-cell:visible")
                .filter(has=page.get_by_text(label, exact=True))
                .last
            )
            assert header.count(), (tab, label)
            for direction in ("ascending", "descending"):
                arrow = header.locator(".sort-caret." + direction).first
                assert arrow.count(), (tab, label, direction)
                header.scroll_into_view_if_needed()
                expected_descending = direction == "descending"
                values = []
                for _ in range(5):
                    values = _visible_numeric_values(page, header, timeout_ms=3_000)
                    is_sorted = len(values) >= 2 and values == sorted(values, reverse=expected_descending)
                    is_active = "is-active" in (arrow.get_attribute("class") or "")
                    if is_active and is_sorted:
                        break
                    # Clicking the locator avoids coordinate hits on nearby tooltip/header
                    # overlays, which can leave the sort arrow and request unchanged.
                    arrow.click(timeout=10_000)
                    header.evaluate("""header => {const table=header.closest('.virtual-pro-table');
                      for (const el of [table,...table.querySelectorAll('*')]) {
                        if (el.scrollHeight>el.clientHeight+1) {const old=el.scrollTop;el.scrollTop=old+1;
                        el.dispatchEvent(new Event('scroll',{bubbles:true}));el.scrollTop=old;
                        el.dispatchEvent(new Event('scroll',{bubbles:true}));}}
                      window.dispatchEvent(new Event('resize'));}""")
                    _wait_for_report_requests_idle(page, pending_report_requests)
                    values = _wait_for_sorted_numeric_values(
                        page, header, arrow, expected_descending, timeout_ms=SORT_RENDER_TIMEOUT_MS
                    )
                arrow_class = arrow.get_attribute("class") or ""
                assert "is-active" in arrow_class, {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "arrowClass": arrow_class,
                    "values": values[:20],
                    "sortRequests": _sort_request_history(report_request_history, endpoints[tab]),
                }
                assert len(values) >= 2, {"tab": tab, "field": label, "values": values}
                assert values == sorted(values, reverse=direction == "descending"), {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "values": values,
                    "sortRequests": _sort_request_history(report_request_history, endpoints[tab]),
                }
                page.get_by_role("button", name="导出", exact=True).first.click()
                menu = "导出类目" if tab == "类目维度" else "导出当前页"
                downloaded_file, export_response, export_request = _download_report_export(
                    page, page.get_by_text(menu, exact=True).last, tab, label, direction
                )
                expected_sort_order = "asc" if direction == "ascending" else "desc"
                assert export_request.get("sortOrder") == expected_sort_order, {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "exportRequest": export_request,
                }
                destination = runtime_dir("downloads") / ("sales_volume_sort_" + uuid4().hex + ".xlsx")
                downloaded_file.save_as(str(destination))
                workbook = load_workbook(destination, read_only=True, data_only=True)
                exported = []
                exported_keys = set()
                exported_detail = Counter()
                dimension_headers = {"店铺维度": "店铺", "发货仓库维度": "发货仓库", "国家维度": "国家"}
                for sheet in workbook:
                    rows = sheet.iter_rows(values_only=True)
                    header_row = [str(value or "").replace("（", "(").replace("）", ")") for value in next(rows)]
                    index = header_row.index(label)
                    key_names = ("类目", "品类") if tab == "类目维度" else ("库存SKU", "SKU编码")
                    key_index = next(i for i, name in enumerate(header_row) if name in key_names)
                    detail_index = header_row.index(dimension_headers[tab]) if tab in dimension_headers else None
                    for row in rows:
                        if row[index] not in (None, ""):
                            exported.append(float(row[index]))
                        if row[key_index] not in (None, ""):
                            key = str(row[key_index])
                            exported_keys.add(key)
                            detail = str(row[detail_index] or "") if detail_index is not None else ""
                            exported_detail[(key, detail)] += 1
                key_field = "className" if tab == "类目维度" else "itemId"
                source_rows = latest_rows.get(tab) or []
                sort_field = export_request.get("sortField")
                sort_order = export_request.get("sortOrder")
                for report_request in reversed(report_request_history):
                    if endpoints[tab] not in report_request.url or report_request.method != "POST":
                        continue
                    try:
                        query_payload = report_request.post_data_json or {}
                    except (TypeError, ValueError):
                        continue
                    if (
                        query_payload.get("pageNum") == export_request.get("pageNum")
                        and query_payload.get("pageSize") == export_request.get("pageSize")
                        and query_payload.get("sortField") == sort_field
                        and query_payload.get("sortOrder") == sort_order
                    ):
                        sorted_response = report_request.response()
                        if sorted_response is not None:
                            source_rows = _assert_report_rows(sorted_response, tab, "sorted search")
                        break
                expected_keys = {str(row[key_field]) for row in source_rows if row.get(key_field) is not None}
                if not expected_keys or exported_keys != expected_keys:
                    visible_row_texts = page.locator(".virtual-pro-table__row:visible").all_inner_texts()
                    visible_lines = {
                        line.strip() for row_text in visible_row_texts for line in row_text.splitlines() if line.strip()
                    }
                    candidate_keys = expected_keys | exported_keys
                    visible_keys = candidate_keys & visible_lines
                    query_history = []
                    for report_request in report_request_history:
                        if "/sales/report/query" not in report_request.url:
                            continue
                        report_response = report_request.response()
                        entry = {"request": _request_diagnostics(report_request)}
                        if report_response is not None:
                            entry["status"] = report_response.status
                            try:
                                report_body = report_response.json()
                            except (TypeError, ValueError):
                                report_body = {}
                            report_rows = report_body.get("rows")
                            if isinstance(report_rows, list):
                                entry["rowCount"] = len(report_rows)
                                entry["keySample"] = [
                                    str(row.get(key_field)) for row in report_rows[:3] if row.get(key_field) is not None
                                ]
                        query_history.append(entry)
                    raise AssertionError(
                        {
                            "tab": tab,
                            "field": label,
                            "direction": direction,
                            "sourceRequest": _request_diagnostics(response.request),
                            "exportRequest": export_request,
                            "exportResponse": export_response,
                            "sourceCount": len(expected_keys),
                            "exportCount": len(exported_keys),
                            "missing": sorted(expected_keys - exported_keys)[:20],
                            "extra": sorted(exported_keys - expected_keys)[:20],
                            "visibleRowCount": len(visible_row_texts),
                            "visibleKeyCount": len(visible_keys),
                            "visibleMissingFromSource": sorted(visible_keys - expected_keys)[:20],
                            "visibleMissingFromExport": sorted(visible_keys - exported_keys)[:20],
                            "visibleRowTextSample": visible_row_texts[:3],
                            "queryHistory": query_history,
                            "download": str(destination),
                        }
                    )
                if tab in dimension_headers:
                    detail_endpoints = {
                        "店铺维度": "queryStoreSalesDimensionExpand",
                        "发货仓库维度": "queryWarehouseSalesDimensionExpand",
                        "国家维度": "queryCountrySalesDimensionExpand",
                    }
                    detail_fields = {
                        "店铺维度": "storeName",
                        "发货仓库维度": "warehouseName",
                        "国家维度": "countryName",
                    }
                    payload = {**latest_payloads[tab], "itemIds": [row["itemId"] for row in source_rows]}
                    detail_response = authenticated_http_client.post(
                        api_base_url.rstrip("/") + "/oms-admin/sales/report/" + detail_endpoints[tab],
                        json=payload,
                        timeout=(10, 180),
                    )
                    detail_response.raise_for_status()
                    body = detail_response.json()
                    assert body.get("code") == 200, body
                    expected_detail = Counter(
                        (str(row["itemId"]), str(row.get(detail_fields[tab]) or "")) for row in body.get("data") or []
                    )
                else:
                    expected_detail = Counter(
                        (str(row[key_field]), "") for row in source_rows if row.get(key_field) is not None
                    )
                assert exported_detail == expected_detail, {
                    "tab": tab,
                    "field": label,
                    "missing": list((expected_detail - exported_detail).elements())[:20],
                    "extra": list((exported_detail - expected_detail).elements())[:20],
                }
                assert len(exported) >= 2, {"tab": tab, "field": label, "download": str(destination)}
                assert exported == sorted(exported, reverse=direction == "descending"), {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "values": exported[:30],
                    "download": str(destination),
                }


def _sort_request_history(requests, endpoint):
    """Keep safe request and numeric response evidence for an ordering failure."""
    numeric_keys = {
        "salesNumber",
        "salesVolume",
        "averageSales",
        "dailySales",
        "stockNumber",
        "stockNum",
        "stockQty",
        "orderNumber",
        "orderCount",
    }
    history = []
    for request in requests:
        if endpoint not in request.url or request.method != "POST":
            continue
        item = {"request": _request_diagnostics(request)}
        response = request.response()
        if response is None:
            item["response"] = None
        else:
            item["status"] = response.status
            try:
                body = response.json()
            except (TypeError, ValueError):
                body = {}
            rows = body.get("rows") if isinstance(body, dict) else None
            if isinstance(rows, list):
                item["rowCount"] = len(rows)
                item["numericValues"] = [
                    {key: row.get(key) for key in numeric_keys if isinstance(row.get(key), (int, float))}
                    for row in rows[:10]
                ]
        history.append(item)
    return history[-10:]

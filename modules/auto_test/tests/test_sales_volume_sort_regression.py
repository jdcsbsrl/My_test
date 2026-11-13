"""Visible numeric sorting for the merged report."""

import json
import os
from collections import Counter
from uuid import uuid4

import pytest
from openpyxl import load_workbook

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


def test_sort_persists_across_pages(logged_in_page, ui_base_url):
    page = logged_in_page
    _open_report(page, ui_base_url)
    page.get_by_text("SKU维度", exact=True).click()
    page.get_by_role("button", name="搜索", exact=True).click()
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


def test_expand_keeps_active_sort(logged_in_page, ui_base_url):
    page = logged_in_page
    _open_report(page, ui_base_url)
    page.get_by_text("类目维度", exact=True).click()
    page.wait_for_timeout(800)
    page.get_by_role("button", name="搜索", exact=True).click()
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
def test_visible_numeric_sort_and_export(logged_in_page, ui_base_url, authenticated_http_client, api_base_url):
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

    def capture(response):
        for tab_name, endpoint in endpoints.items():
            if endpoint in response.url and response.request.method == "POST":
                try:
                    body = response.json()
                    if body.get("code") == 200 and isinstance(body.get("rows"), list):
                        latest_rows[tab_name] = body["rows"]
                        latest_payloads[tab_name] = response.request.post_data_json
                except (ValueError, TypeError):
                    pass

    page.on("response", capture)
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    page.reload(wait_until="domcontentloaded")
    page.get_by_text("SKU维度", exact=True).first.wait_for(state="visible", timeout=30000)
    tabs = ["SKU维度", "店铺维度", "发货仓库维度", "国家维度", "类目维度"]
    if os.environ.get("SALES_VOLUME_ROLE") == "procurement":
        tabs.remove("店铺维度")
    for tab in tabs:
        page.get_by_text(tab, exact=True).click()
        page.get_by_role("button", name="搜索", exact=True).click()
        page.wait_for_timeout(1200)
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
                for _ in range(5):
                    if "is-active" in (arrow.get_attribute("class") or ""):
                        break
                    box = arrow.bounding_box()
                    assert box, (tab, label, direction)
                    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                    page.wait_for_timeout(1500)
                assert "is-active" in (arrow.get_attribute("class") or ""), (tab, label, direction)
                page.wait_for_timeout(3000)
                header.evaluate("""header => {const table=header.closest('.virtual-pro-table');
                  for (const el of [table,...table.querySelectorAll('*')]) {
                    if (el.scrollHeight>el.clientHeight+1) {const old=el.scrollTop;el.scrollTop=old+1;
                    el.dispatchEvent(new Event('scroll',{bubbles:true}));el.scrollTop=old;
                    el.dispatchEvent(new Event('scroll',{bubbles:true}));}}
                  window.dispatchEvent(new Event('resize'));}""")
                page.wait_for_timeout(800)
                assert "is-active" in (arrow.get_attribute("class") or ""), (tab, label, direction)
                values = header.evaluate("""header => {
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
                }""")
                assert len(values) >= 2, {"tab": tab, "field": label, "values": values}
                assert values == sorted(values, reverse=direction == "descending"), {
                    "tab": tab,
                    "field": label,
                    "direction": direction,
                    "values": values,
                }
                page.get_by_role("button", name="导出", exact=True).first.click()
                menu = "导出类目" if tab == "类目维度" else "导出当前页"
                with page.expect_download(timeout=180000) as download:
                    page.get_by_text(menu, exact=True).last.click()
                destination = runtime_dir("downloads") / ("sales_volume_sort_" + uuid4().hex + ".xlsx")
                download.value.save_as(str(destination))
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
                source_rows = latest_rows.get(tab) or []
                key_field = "className" if tab == "类目维度" else "itemId"
                expected_keys = {str(row[key_field]) for row in source_rows if row.get(key_field) is not None}
                assert expected_keys and exported_keys == expected_keys, {
                    "tab": tab,
                    "field": label,
                    "missing": sorted(expected_keys - exported_keys),
                    "extra": sorted(exported_keys - expected_keys),
                    "download": str(destination),
                }
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

"""Regression checks for the merged product sales report (requirement 1003420)."""

from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
import json
import os
import re
import time

import pytest
from openpyxl import load_workbook

from modules.auto_test.api.inventory_sku_api import InventorySKUAPI
from modules.auto_test.api.sku_group_api import SKUGroupAPI
from modules.auto_test.core.sales_volume_contract import (
    DIMENSIONS,
    aggregate_orders,
    build_completed_report_window,
    build_export_task_name,
    build_filter,
    category_order_counts,
    export_task_id,
    find_new_export_task,
    list_export_tasks,
    group_sales_by_sku,
    order_source_breakdown,
    order_item_rows,
)


@pytest.fixture
def report_window():
    return build_completed_report_window(os.environ.get("SALES_VOLUME_AS_OF_DATE"))


@pytest.fixture
def report_query(authenticated_http_client, api_base_url):
    def query(endpoint, payload):
        response = authenticated_http_client.post(
            api_base_url.rstrip("/") + "/oms-admin/sales/report/" + endpoint,
            json=payload,
            timeout=(10, 180),
        )
        response.raise_for_status()
        return response.json()

    return query


@pytest.mark.parametrize("dimension", ["sku", "store", "warehouse", "country", "category"])
def test_dimension_accepts_payment_range(report_query, report_window, dimension):
    payload = {**build_filter(pay_range=report_window), "pageNum": 1, "pageSize": 50}
    response = report_query(DIMENSIONS[dimension], payload)
    assert response.get("code") == 200, response
    assert isinstance(response.get("rows"), list), response
    assert isinstance(response.get("total"), int), response


def test_time_filter_requires_at_least_one_time(report_query):
    response = report_query(
        DIMENSIONS["sku"],
        {
            "classIds": [],
            "customClassIds": [],
            "salesStatuses": [],
            "creatorIds": [],
            "storeIds": [],
            "pageNum": 1,
            "pageSize": 50,
        },
    )
    assert response.get("code") != 200 and "至少" in str(response.get("msg", "")), response


def test_payment_and_shipping_time_filters(report_query, report_window):
    base = {"pageNum": 1, "pageSize": 50}
    shipping = report_query(DIMENSIONS["sku"], {**build_filter(ship_range=report_window), **base})
    both = report_query(
        DIMENSIONS["sku"],
        {
            **build_filter(pay_range=report_window, ship_range=report_window),
            **base,
        },
    )
    assert shipping.get("code") == both.get("code") == 200, (shipping, both)
    assert both.get("total", 0) <= shipping.get("total", 0), (shipping, both)


def test_sku_daily_sales_uses_selected_calendar_days(report_query, report_window, sold_store_ids):
    payload = {**build_filter(report_window, store_ids=sold_store_ids), "pageNum": 1, "pageSize": 500}
    body = report_query(DIMENSIONS["sku"], payload)
    assert body.get("code") == 200, body
    rows = body.get("rows") or []
    assert rows and len(rows) == body.get("total") <= 500, "No SKU sample or incomplete pagination"
    days = (datetime.fromisoformat(report_window[1]).date() - datetime.fromisoformat(report_window[0]).date()).days + 1
    for row in rows:
        expected = Decimal(str(row.get("salesNumber") or 0)) / days
        actual = Decimal(str(row.get("dayAverageSalesNumber") or 0))
        assert abs(expected - actual) <= Decimal("0.005"), {
            "sku": row.get("itemId"),
            "expected": expected,
            "actual": actual,
        }


def test_half_year_time_boundary(report_query):
    base = {
        "classIds": [],
        "customClassIds": [],
        "salesStatuses": [],
        "creatorIds": [],
        "storeIds": [],
        "pageNum": 1,
        "pageSize": 10,
    }
    exact = report_query(
        DIMENSIONS["sku"],
        {
            **base,
            "payTimeBegin": "2026-04-10 00:00:00",
            "payTimeEnd": "2026-10-10 00:00:00",
        },
    )
    over = report_query(
        DIMENSIONS["sku"],
        {
            **base,
            "payTimeBegin": "2026-04-09 23:59:59",
            "payTimeEnd": "2026-10-10 00:00:00",
        },
    )
    assert exact.get("code") == 200, exact
    assert over.get("code") != 200 and "6个月" in str(over.get("msg", "")), over


def test_create_time_filter_limits_result(report_query, report_window):
    baseline = report_query(
        DIMENSIONS["sku"],
        {**build_filter(report_window), "pageNum": 1, "pageSize": 500},
    )
    assert baseline.get("code") == 200, baseline
    rows = baseline.get("rows") or []
    sample = next((row for row in rows if row.get("createTime")), None)
    assert sample, "No SKU create time sample: create-time filter remains unverified"
    day = str(sample["createTime"])[:10]
    filtered = report_query(
        DIMENSIONS["sku"],
        {
            **build_filter(report_window, create_range=(f"{day} 00:00:00", f"{day} 23:59:59")),
            "pageNum": 1,
            "pageSize": 500,
        },
    )
    assert filtered.get("code") == 200, filtered
    day_rows = filtered.get("rows") or []
    assert day_rows, {"createTime": day, "message": "Create-time window returned no rows"}
    assert all(str(row.get("createTime") or "").startswith(day) for row in day_rows), {
        "createTime": day,
        "rows": day_rows[:5],
    }
    assert int(filtered.get("total") or 0) <= int(baseline.get("total") or 0), {
        "createTime": day,
        "filtered": filtered.get("total"),
        "baseline": baseline.get("total"),
    }
    empty = report_query(
        DIMENSIONS["sku"],
        {
            **build_filter(report_window, create_range=("2000-01-01 00:00:00", "2000-01-02 23:59:59")),
            "pageNum": 1,
            "pageSize": 50,
        },
    )
    assert empty.get("code") == 200 and empty.get("total") == 0 and not empty.get("rows"), empty


def test_sku_filters_and_invalid_inputs(report_query, report_window):
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    baseline = report_query(DIMENSIONS["sku"], payload)
    assert baseline.get("code") == 200, baseline
    rows = baseline.get("rows") or []
    candidate = next(
        (
            row
            for row in rows
            if len(str(row.get("itemId") or "")) >= 5
            and row.get("mainSkuId")
            and row.get("classId")
            and row.get("salesStatus") is not None
        ),
        None,
    )
    assert candidate, "No SKU sample for filter checks"
    sku = str(candidate["itemId"])
    filters = [
        ({"skuCode": sku}, lambda row: sku.lower() in str(row.get("itemId") or "").lower()),
        ({"mainSkuId": candidate["mainSkuId"]}, lambda row: row.get("mainSkuId") == candidate["mainSkuId"]),
        ({"classIds": [candidate["classId"]]}, lambda row: str(row.get("classId")) == str(candidate["classId"])),
        (
            {"salesStatuses": [candidate["salesStatus"]]},
            lambda row: str(row.get("salesStatus")) == str(candidate["salesStatus"]),
        ),
    ]
    for extra, matches in filters:
        body = report_query(DIMENSIONS["sku"], {**payload, **extra})
        assert body.get("code") == 200, body
        found = body.get("rows") or []
        assert found and all(matches(row) for row in found), {"filter": extra, "rows": found[:10]}
    name_sample = next((row for row in rows if len(str(row.get("displayName") or "")) >= 5), None)
    assert name_sample, "No product-name sample for fuzzy search"
    name_fragment = str(name_sample["displayName"])[:5]
    name_result = report_query(DIMENSIONS["sku"], {**payload, "skuName": name_fragment})
    assert name_result.get("code") == 200, name_result
    names = name_result.get("rows") or []
    assert names and all(
        name_fragment.lower() in str(row.get("displayName") or "").lower()
        or name_fragment.lower() in str(row.get("englishName") or "").lower()
        for row in names
    ), {"fragment": name_fragment, "rows": names[:10]}
    for field in ("skuCode", "skuName"):
        body = report_query(DIMENSIONS["sku"], {**payload, field: "ABCD"})
        assert body.get("code") != 200 and "5" in str(body.get("msg", "")), body
    empty = report_query(DIMENSIONS["sku"], {**payload, "skuCode": "NO-SUCH-SKU-1003420"})
    assert empty.get("code") == 200 and empty.get("total") == 0 and not empty.get("rows"), empty


@pytest.mark.parametrize(
    "bounds", [{"salesNumberMin": 1}, {"salesNumberMax": 100}, {"salesNumberMin": 1, "salesNumberMax": 100}]
)
def test_sku_sales_range_filters(report_query, report_window, bounds):
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 100, **bounds}
    body = report_query(DIMENSIONS["sku"], payload)
    assert body.get("code") == 200, body
    rows = body.get("rows") or []
    assert rows, {"bounds": bounds, "message": "No sample; range filter remains unverified"}
    for row in rows:
        sales = Decimal(str(row.get("salesNumber") or 0))
        assert sales >= bounds.get("salesNumberMin", sales), row
        assert sales <= bounds.get("salesNumberMax", sales), row


def test_creator_dropdown_matches_dictionary_order(logged_in_page, ui_base_url):
    page = logged_in_page
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    dictionaries = []

    def on_response(response):
        if "/system/dict/data/type/sys_user_username" in response.url:
            try:
                dictionaries.append(response.json())
            except Exception:  # noqa: BLE001
                return

    page.on("response", on_response)
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    page.reload(wait_until="domcontentloaded")
    page.get_by_text("SKU维度", exact=True).first.wait_for(state="visible", timeout=30000)
    field = (
        page.locator(".el-form-item:visible").filter(has=page.locator(".el-form-item__label", has_text="创建人")).first
    )
    field.locator(".keyword-select-trigger").click()
    page.wait_for_timeout(2000)
    overlay = page.locator(".el-dialog:visible, .el-popper:visible, [role='dialog']:visible").first
    overlay.wait_for(state="visible", timeout=10000)
    assert dictionaries and dictionaries[-1].get("code") == 200, dictionaries
    labels = [str(item.get("dictLabel")) for item in dictionaries[-1].get("data") or [] if item.get("dictLabel")]
    assert len(labels) > 5, "Creator dictionary has no user sample"

    def visible_options():
        lines = [text.strip() for text in overlay.inner_text().splitlines() if text.strip()]
        return [line for line in lines if line != "显示已停用用户"]

    options = visible_options()
    assert options[:5] == labels[:5], {"options": options[:5], "dictionary": labels[:5]}
    assert [label for label in options[:20] if label in labels] == labels[: len(options[:20])], {
        "message": "Dropdown order differs from the dictionary order",
        "options": options[:20],
        "dictionary": labels[:20],
    }
    toggle = overlay.locator(".el-checkbox").filter(has_text="显示已停用用户").first
    assert toggle.count(), "Disabled-user toggle is missing"
    toggle.click()
    page.wait_for_timeout(2000)
    after = visible_options()
    assert after[:5] == options[:5], {"before": options[:5], "after": after[:5]}


def test_creator_filter_matches_dictionary_user(authenticated_http_client, api_base_url, report_query, report_window):
    response = authenticated_http_client.get(
        api_base_url.rstrip("/") + "/oms-admin/system/dict/data/type/sys_user_username", timeout=(10, 90)
    )
    response.raise_for_status()
    users = response.json()
    assert users.get("code") == 200 and users.get("data"), users
    user_ids = {
        str(item.get("dictLabel")): str(item.get("dictValue")) for item in users["data"] if item.get("dictValue")
    }
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    baseline = report_query(DIMENSIONS["sku"], payload)
    assert baseline.get("code") == 200, baseline
    candidate = next((row for row in baseline.get("rows") or [] if row.get("createByName") in user_ids), None)
    assert candidate, "No SKU creator can be matched to dictionary; creator filter incomplete"
    name = candidate["createByName"]
    body = report_query(DIMENSIONS["sku"], {**payload, "creatorIds": [user_ids[name]]})
    assert body.get("code") == 200, body
    rows = body.get("rows") or []
    assert rows and all(row.get("createByName") == name for row in rows), {"creator": name, "rows": rows[:10]}


def test_supplier_name_filter_matches_rows(report_query, report_window):
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    baseline = report_query(DIMENSIONS["sku"], payload)
    assert baseline.get("code") == 200, baseline
    rows = baseline.get("rows") or []
    supplier = next((str(row.get("defaultSupplier")) for row in rows if row.get("defaultSupplier")), None)
    assert supplier and len(supplier) >= 2, "No default supplier sample; supplier filter remains unverified"
    fragment = supplier[:2]
    filtered = report_query(DIMENSIONS["sku"], {**payload, "supplierName": fragment})
    assert filtered.get("code") == 200, filtered
    matched = filtered.get("rows") or []
    assert matched, {"supplier": fragment, "message": "Known supplier fragment returned no rows"}
    assert all(fragment in str(row.get("defaultSupplier") or "") for row in matched), {
        "supplier": fragment,
        "rows": matched[:5],
    }
    assert int(filtered.get("total") or 0) <= int(baseline.get("total") or 0), {
        "filtered": filtered.get("total"),
        "baseline": baseline.get("total"),
    }
    empty = report_query(DIMENSIONS["sku"], {**payload, "supplierName": "NO-SUCH-SUPPLIER-1003420"})
    assert empty.get("code") == 200 and empty.get("total") == 0 and not empty.get("rows"), empty


def test_custom_class_filter_matches_rows(report_query, report_window):
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    baseline = report_query(DIMENSIONS["sku"], payload)
    assert baseline.get("code") == 200, baseline
    sample = next((row for row in baseline.get("rows") or [] if row.get("customClassId")), None)
    if sample is None:
        pytest.fail("INCOMPLETE: no SKU carries a custom class in this window; custom-class filter stays unverified")
    custom_id = str(sample["customClassId"]).split(",")[0].strip()
    assert custom_id, "INCOMPLETE: custom class identifier is empty"
    filtered = report_query(DIMENSIONS["sku"], {**payload, "customClassIds": [custom_id]})
    assert filtered.get("code") == 200, filtered
    matched = filtered.get("rows") or []
    assert matched, {"customClassId": custom_id, "message": "Custom-class filter returned no rows"}
    assert all(
        custom_id in {item.strip() for item in str(row.get("customClassId") or "").split(",")} for row in matched
    ), {
        "customClassId": custom_id,
        "rows": matched[:5],
    }


def test_new_page_tabs_and_store_filter(logged_in_page, ui_base_url):
    page = logged_in_page
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    for tab in ("SKU维度", "发货仓库维度", "国家维度", "类目维度"):
        page.get_by_text(tab, exact=True).click(timeout=30000)
        field = page.locator(".el-form-item:visible").filter(has=page.locator(".el-form-item__label", has_text="店铺"))
        assert field.count() == 1, tab


def _dimension_filter_store_scope(role, resolve_store_ids):
    """Procurement can filter warehouse/country without store permission."""
    if str(role or "").strip().lower() == "procurement":
        return []
    return resolve_store_ids()


@pytest.fixture
def dimension_filter_store_ids(request):
    role = os.getenv("SALES_VOLUME_ROLE", "admin")
    return _dimension_filter_store_scope(role, lambda: request.getfixturevalue("sold_store_ids"))


@pytest.fixture
def sold_store_ids(report_query, report_window, authenticated_http_client, api_base_url):
    response = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/base/store/queryPermissionStoreList",
        json={},
        timeout=(10, 90),
    )
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, body
    stores = body.get("data") or []
    assert len(stores) >= 2, "Insufficient permitted stores: store multi-select not verified"
    base = {"pageNum": 1, "pageSize": 50}
    candidates = []
    for store in stores[:50]:
        if str(store.get("storeStatus")) != "1":
            continue
        candidate = str(store["id"])
        result = report_query(
            DIMENSIONS["sku"],
            {
                **build_filter(report_window, store_ids=[candidate]),
                **base,
            },
        )
        assert result.get("code") == 200, result
        if float(result.get("salesVolume") or 0) > 0:
            candidates.append(candidate)
        if len(candidates) == 2:
            break
    assert len(candidates) == 2, "Insufficient sold-store samples: multi-store check incomplete"
    return candidates


def _normalize_store_name(value):
    return re.sub(r"[\u200b-\u200d\ufeff\s]+", "", str(value or "")).casefold()


def _visible_store_item_names(popover):
    items = popover.locator(".store-item:visible")
    names = []
    for index in range(items.count()):
        item = items.nth(index)
        name = item.locator(".store-name").first
        text = name.text_content() if name.count() else item.text_content()
        if text:
            names.append(text.strip())
    return names


def _store_picker_group_names(summary):
    lines = [line.strip() for line in str(summary or "").splitlines() if line.strip()]
    return [lines[index] for index in range(len(lines) - 1) if re.fullmatch(r"\(\d+\)", lines[index + 1])]


def _set_store_picker_item(page, popover, search, store_name, selected):
    expected_name = _normalize_store_name(store_name)
    page.wait_for_function(
        """
        () => Array.from(document.querySelectorAll('.store-select-popover'))
          .some(popover => /\\(\\s*\\d+\\s*\\)/.test(popover.innerText));
        """,
        timeout=10000,
    )
    group_names = _store_picker_group_names(popover.inner_text())
    groups = group_names or [None]
    found = False
    for group_name in groups:
        if group_name:
            group = popover.get_by_text(group_name, exact=True).first
            group.click(force=True)
        search.fill(store_name)
        try:
            page.wait_for_function(
                """
                (expectedName) => {
                  const normalize = value => (value || '')
                    .replace(/[\\u200B-\\u200D\\uFEFF]/g, '')
                    .replace(/\\s+/g, '').trim().toLocaleLowerCase();
                  const visible = element => {
                    const rect = element.getBoundingClientRect();
                    const style = window.getComputedStyle(element);
                    return rect.width > 0 && rect.height > 0
                      && style.visibility !== 'hidden' && style.display !== 'none';
                  };
                  const popover = Array.from(document.querySelectorAll('.store-select-popover'))
                    .find(visible);
                  if (!popover) return false;
                  return Array.from(popover.querySelectorAll('.store-item'))
                    .filter(visible)
                    .some(
                      item => normalize(item.querySelector('.store-name')?.textContent)
                        === normalize(expectedName),
                    );
                }
                """,
                arg=store_name,
                timeout=2500,
            )
            found = True
            break
        except Exception:
            continue
    if not found:
        summary = popover.inner_text()[:500]
        raise AssertionError(
            f"店铺搜索结果未显示目标选项：name={store_name!r}; "
            f"搜索分组={group_names!r}; 可见选项={_visible_store_item_names(popover)!r}; 下拉摘要={summary!r}"
        )

    items = popover.locator(".store-item:visible")
    matches = []
    for index in range(items.count()):
        item = items.nth(index)
        name = item.locator(".store-name").first
        text = name.text_content() if name.count() else item.text_content()
        if _normalize_store_name(text) == expected_name:
            matches.append(item)
    assert len(matches) == 1, {
        "store": store_name,
        "matchingOptions": len(matches),
        "visibleOptions": _visible_store_item_names(popover),
    }

    item = matches[0]
    checkbox = item.locator('input[type="checkbox"]').first
    if checkbox.count():
        if checkbox.is_checked() != selected:
            visual_checkbox = item.locator(".el-checkbox__inner:visible").first
            if visual_checkbox.count():
                visual_checkbox.click(force=True)
            else:
                item.click(force=True)
        assert checkbox.is_checked() is selected, {"store": store_name, "selected": selected}
        return

    aria_checkbox = item.locator('[role="checkbox"]').first
    if aria_checkbox.count():
        current = aria_checkbox.get_attribute("aria-checked") == "true"
        if current != selected:
            aria_checkbox.click(force=True)
        return

    item.click(force=True)


def test_store_filter_must_not_increase_sales(report_query, report_window, sold_store_ids):
    ids = sold_store_ids
    base = {"pageNum": 1, "pageSize": 50}
    for dimension in ("sku", "warehouse", "country", "category"):
        filtered = report_query(DIMENSIONS[dimension], {**build_filter(report_window, store_ids=ids), **base})
        unfiltered = report_query(DIMENSIONS[dimension], {**build_filter(report_window), **base})
        assert filtered.get("code") == unfiltered.get("code") == 200, (filtered, unfiltered)
        assert float(filtered.get("salesVolume") or 0) <= float(unfiltered.get("salesVolume") or 0), dimension


@pytest.mark.parametrize("dimension", ["sku", "store", "warehouse", "country", "category"])
def test_filtered_pagination_and_sales_total(report_query, report_window, sold_store_ids, dimension):
    stores = [] if dimension == "category" else sold_store_ids
    payload = {**build_filter(report_window, store_ids=stores), "pageNum": 1, "pageSize": 500}
    full = report_query(DIMENSIONS[dimension], payload)
    assert full.get("code") == 200, full
    rows = full.get("rows") or []
    assert len(rows) > 1 and len(rows) == full.get("total") <= 500, "No multipage sample or incomplete result"
    expected_sales = sum(Decimal(str(row.get("salesNumber") or 0)) for row in rows)
    assert expected_sales == Decimal(str(full.get("salesVolume") or 0)), dimension
    small_size = 1
    first = report_query(DIMENSIONS[dimension], {**payload, "pageSize": small_size})
    second = report_query(DIMENSIONS[dimension], {**payload, "pageNum": 2, "pageSize": small_size})
    assert first.get("code") == second.get("code") == 200, (first, second)
    assert first.get("total") == second.get("total") == full.get("total"), dimension
    assert len(first.get("rows") or []) == len(second.get("rows") or []) == small_size, dimension
    key = "classId" if dimension == "category" else "itemId"
    assert first["rows"][0].get(key) != second["rows"][0].get(key), dimension
    assert Decimal(str(first.get("salesVolume") or 0)) == expected_sales, dimension


@pytest.mark.parametrize(
    "tab,dimension",
    [
        ("SKU维度", "sku"),
        ("发货仓库维度", "warehouse"),
        ("国家维度", "country"),
        ("类目维度", "category"),
    ],
)
def test_ui_multistore_search_and_reset(
    logged_in_page,
    ui_base_url,
    authenticated_http_client,
    api_base_url,
    report_window,
    sold_store_ids,
    tab,
    dimension,
):
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    store_response = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/base/store/queryPermissionStoreList",
        json={},
        timeout=(10, 90),
    )
    store_response.raise_for_status()
    store_body = store_response.json()
    assert store_body.get("code") == 200, store_body
    names = {str(store["id"]): store["storeName"] for store in store_body.get("data") or []}
    assert all(store_id in names for store_id in sold_store_ids), names
    page = logged_in_page
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    page.get_by_text(tab, exact=True).click(timeout=30000)
    field = (
        page.locator(".el-form-item:visible").filter(has=page.locator(".el-form-item__label", has_text="店铺")).first
    )
    field.locator(".store-select-trigger").click()
    popover = page.locator(".store-select-popover:visible").first
    search = popover.locator('input[placeholder*="店铺"]').first
    for store_id in sold_store_ids:
        name = names[store_id]
        _set_store_picker_item(page, popover, search, name, selected=True)
    page.keyboard.press("Escape")
    pay = page.locator(".el-form-item:visible").filter(has_text="订单付款时间").first.locator("input")
    for index, value in enumerate(report_window):
        pay.nth(index).evaluate("element => element.removeAttribute('readonly')")
        pay.nth(index).fill(value)
        pay.nth(index).press("Tab")
    page.keyboard.press("Escape")
    with page.expect_response(lambda response: DIMENSIONS[dimension] in response.url, timeout=120000) as captured:
        page.get_by_role("button", name="搜索", exact=True).click()
    response = captured.value
    assert response.json().get("code") == 200, response.text()
    request = response.request.post_data_json
    assert set(request.get("storeIds") or []) == set(sold_store_ids), request
    assert request.get("payTimeBegin") == report_window[0] and request.get("payTimeEnd") == report_window[1], request
    page.get_by_role("button", name="重置", exact=True).click()
    assert all(name not in field.inner_text() for name in names.values() if name), field.inner_text()


def test_store_single_select_and_clear(logged_in_page, ui_base_url, authenticated_http_client, api_base_url):
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    stores = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/base/store/queryPermissionStoreList", json={}, timeout=(10, 90)
    ).json()
    enabled_stores = [
        row for row in stores.get("data") or [] if row.get("storeName") and str(row.get("storeStatus")) == "1"
    ]
    assert enabled_stores, "No enabled permitted store for the single-select check"
    target_id = str(enabled_stores[0]["id"])
    target_name = str(enabled_stores[0]["storeName"])
    page = logged_in_page
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    page.get_by_text("SKU维度", exact=True).first.wait_for(state="visible", timeout=30000)
    field = (
        page.locator(".el-form-item:visible").filter(has=page.locator(".el-form-item__label", has_text="店铺")).first
    )

    def search_store_ids():
        with page.expect_response(
            lambda response: "/sales/report/" in response.url and response.request.method == "POST", timeout=120000
        ) as captured:
            page.get_by_role("button", name="搜索", exact=True).click()
        return json.loads(captured.value.request.post_data or "{}").get("storeIds")

    field.locator(".store-select-trigger").click()
    popover = page.locator(".store-select-popover:visible").first
    search = popover.locator('input[placeholder*="店铺"]').first
    _set_store_picker_item(page, popover, search, target_name, selected=True)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assert search_store_ids() == [target_id], {"store": target_name}

    field.locator(".store-select-trigger").click()
    popover = page.locator(".store-select-popover:visible").first
    popover.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(800)
    has_clear = "清除已选" in popover.inner_text()
    search = popover.locator('input[placeholder*="店铺"]').first
    _set_store_picker_item(page, popover, search, target_name, selected=False)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    assert search_store_ids() == [], {
        "store": target_name,
        "clearControl": has_clear,
        "message": "Clearing one store kept the filter",
    }


@pytest.mark.parametrize(
    "dimension,endpoint",
    [
        ("store", "queryStoreSalesDimensionExpand"),
        ("warehouse", "queryWarehouseSalesDimensionExpand"),
        ("country", "queryCountrySalesDimensionExpand"),
    ],
)
def test_multistore_expand_sales_matches_sku_list(report_query, report_window, sold_store_ids, dimension, endpoint):
    payload = {**build_filter(report_window, store_ids=sold_store_ids), "pageNum": 1, "pageSize": 500}
    listing = report_query(DIMENSIONS[dimension], payload)
    assert listing.get("code") == 200, listing
    rows = listing.get("rows") or []
    assert rows and len(rows) == listing.get("total"), "No sample or pagination incomplete"
    ids = [row["itemId"] for row in rows]
    assert len(ids) == len(set(ids)), "Duplicate SKU in listing"
    expanded = report_query(endpoint, {**payload, "itemIds": ids})
    assert expanded.get("code") == 200, expanded
    totals = group_sales_by_sku(expanded.get("data") or [])
    expected = group_sales_by_sku(rows)
    assert totals == expected, {"dimension": dimension, "listing": expected, "detail": totals}


def test_multistore_category_detail_sales(report_query, report_window, sold_store_ids):
    payload = {**build_filter(report_window, store_ids=sold_store_ids), "pageNum": 1, "pageSize": 500}
    categories = report_query(DIMENSIONS["category"], payload)
    assert categories.get("code") == 200, categories
    rows = categories.get("rows") or []
    assert rows and len(rows) == categories.get("total"), "No category sample or pagination incomplete"
    for category in rows:
        category_id = category.get("classId")
        detail = report_query("queryCategorySalesDimensionExpand", {**payload, "classIds": [category_id]})
        assert detail.get("code") == 200, detail
        items = detail.get("data") or []
        assert items, {"classId": category_id, "error": "No expanded SKU sample"}
        sales = sum(float(item.get("salesNumber") or 0) for item in items)
        assert sales == float(category.get("salesNumber") or 0), {"category": category, "items": items}
        inventory = sum(Decimal(str(item.get("stockNumber") or 0)) for item in items)
        assert inventory == Decimal(str(category.get("stockNumber") or 0)), {"category": category, "items": items}
        detail_orders = sum(int(item.get("orderNumber") or 0) for item in items)
        assert detail_orders >= int(category.get("orderNumber") or 0), {"category": category, "items": items}


@pytest.mark.parametrize(
    "dimension,filter_key,detail_key,dict_path",
    [
        ("warehouse", "locationIds", "warehouseName", "/oms-admin/system/dict/data/type/oms_location"),
        ("country", "countryCodes", "countryCode", None),
    ],
)
def test_dimension_specific_filter(
    authenticated_http_client,
    api_base_url,
    report_query,
    report_window,
    dimension_filter_store_ids,
    dimension,
    filter_key,
    detail_key,
    dict_path,
):
    payload = {
        **build_filter(report_window, store_ids=dimension_filter_store_ids),
        "pageNum": 1,
        "pageSize": 500,
    }
    listing = report_query(DIMENSIONS[dimension], payload)
    assert listing.get("code") == 200, listing
    rows = listing.get("rows") or []
    assert rows and len(rows) == listing.get("total"), "No sample or incomplete pagination"
    endpoint = "queryWarehouseSalesDimensionExpand" if dimension == "warehouse" else "queryCountrySalesDimensionExpand"
    expanded = report_query(endpoint, {**payload, "itemIds": [row["itemId"] for row in rows]})
    assert expanded.get("code") == 200, expanded
    positive = [
        row for row in expanded.get("data") or [] if row.get(detail_key) and float(row.get("salesNumber") or 0) > 0
    ]
    assert positive, {"dimension": dimension, "message": "No positive dimension sample"}
    if dict_path:
        response = authenticated_http_client.get(api_base_url.rstrip("/") + dict_path, timeout=(10, 90))
        response.raise_for_status()
        body = response.json()
        assert body.get("code") == 200, body
        mapping = {str(item.get("dictLabel")): str(item.get("dictValue")) for item in body.get("data") or []}
        candidate = next((row for row in positive if str(row[detail_key]) in mapping), None)
        assert candidate, "No sold warehouse matches the warehouse dictionary"
        selected = mapping[str(candidate[detail_key])]
    else:
        candidate = positive[0]
        selected = str(candidate[detail_key])
    filtered = report_query(DIMENSIONS[dimension], {**payload, filter_key: [selected]})
    assert filtered.get("code") == 200 and filtered.get("rows"), filtered
    filtered_details = report_query(
        endpoint, {**payload, filter_key: [selected], "itemIds": [row["itemId"] for row in filtered["rows"]]}
    )
    assert filtered_details.get("code") == 200, filtered_details
    positive_details = [row for row in filtered_details.get("data") or [] if float(row.get("salesNumber") or 0) > 0]
    assert positive_details and all(
        str(row.get(detail_key)) == str(candidate[detail_key]) for row in positive_details
    ), positive_details


def test_warehouse_zero_sales_stock_is_in_expansion(report_query, report_window):
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    listing = report_query(DIMENSIONS["warehouse"], payload)
    assert listing.get("code") == 200, listing
    rows = listing.get("rows") or []
    assert rows, "No SKU sample to verify warehouse stock"
    expanded = report_query(
        "queryWarehouseSalesDimensionExpand",
        {
            **payload,
            "itemIds": [row["itemId"] for row in rows],
        },
    )
    assert expanded.get("code") == 200, expanded
    details = expanded.get("data") or []
    candidate = next(
        (row for row in details if float(row.get("salesNumber") or 0) == 0 and float(row.get("stockNumber") or 0) > 0),
        None,
    )
    assert candidate, "No zero-sales warehouse with stock; warehouse reconciliation incomplete"
    sku = candidate["itemId"]
    summary = next(row for row in rows if row["itemId"] == sku)
    stocks = sum(Decimal(str(row.get("stockNumber") or 0)) for row in details if row.get("itemId") == sku)
    assert stocks == Decimal(str(summary.get("stockNumber") or 0)), {"summary": summary, "detailStock": stocks}


def _fetch_order_data(authenticated_http_client, api_base_url, report_window, sold_store_ids, item_ids=None):
    session = authenticated_http_client
    root = api_base_url.rstrip("/")
    order_payload = {
        "orderId": "",
        "orderNo": "",
        "orderByColumn": "",
        "isAsc": "",
        "platform": "",
        "shopifyLocationId": "",
        "fixedClassId": [],
        "itemIds": item_ids or [],
        "customerClassBoList": [],
        "trackingStatus": "",
        "deptId": None,
        "pageNum": 1,
        "pageSize": 500,
        "orderStatus": "",
        "storeIds": ",".join(sold_store_ids),
        "itemAttribute": "",
        "exceptionClassIds": "",
        "customClassIds": "",
        "countryCode": "",
        "onlyShowMyProcessing": "0",
        "queryType": "0",
        "payTimeBegin": report_window[0],
        "payTimeEnd": report_window[1],
    }
    orders = []
    for page in range(1, 201):
        order_payload["pageNum"] = page
        order_response = session.post(
            root + "/oms-admin/sales/order/batchListNew", json=order_payload, timeout=(10, 180)
        )
        order_response.raise_for_status()
        order_body = order_response.json()
        assert order_body.get("code") == 200, order_body
        table = order_body["data"]["tableDataInfo"]
        page_rows = table.get("rows") or []
        orders.extend(page_rows)
        if len(orders) >= table["total"]:
            break
        assert page_rows, "Order pagination incomplete"
    assert orders and len(orders) == table["total"], "No order sample or pagination incomplete"
    numbers = [str(order["orderNo"]) for order in orders]
    assert len(numbers) == len(set(numbers)), "Duplicate order number"
    details = {}
    for start in range(0, len(numbers), 100):
        response = session.post(
            root + "/oms-admin/sales/orderItem/queryAllList",
            json={"orderNoList": numbers[start : start + 100]},
            timeout=(10, 180),
        )
        response.raise_for_status()
        body = response.json()
        assert body.get("code") == 200, body
        details.update(body.get("data") or {})
    return orders, details


@pytest.fixture
def sold_order_data(authenticated_http_client, api_base_url, report_window, sold_store_ids):
    return _fetch_order_data(authenticated_http_client, api_base_url, report_window, sold_store_ids)


def _assert_sku_sales_match_order_source(
    report_query, report_window, store_ids, orders, details, order_source_client, api_base_url
):
    source = aggregate_orders(orders, details)
    payload = {**build_filter(report_window, store_ids=store_ids), "pageNum": 1, "pageSize": 500}
    report = report_query(DIMENSIONS["sku"], payload)
    assert report.get("code") == 200, report
    rows = report.get("rows") or []
    assert rows and len(rows) == report.get("total") <= 500, "No SKU sample or pagination incomplete"
    actual = {
        str(row["itemId"]): {"sales": int(row.get("salesNumber") or 0), "orders": int(row.get("orderQuantity") or 0)}
        for row in rows
    }
    missing = {"sales": 0, "orders": 0}
    mismatched_skus = sorted(
        sku for sku in set(actual) | set(source) if actual.get(sku, missing) != source.get(sku, missing)
    )
    if mismatched_skus:
        rechecked_orders, rechecked_details = _fetch_order_data(
            order_source_client,
            api_base_url,
            report_window,
            store_ids,
            item_ids=mismatched_skus,
        )
        rechecked_source = aggregate_orders(rechecked_orders, rechecked_details)
        rechecked_report_body = report_query(DIMENSIONS["sku"], payload)
        assert rechecked_report_body.get("code") == 200, rechecked_report_body
        rechecked_report = {
            str(row["itemId"]): {
                "sales": int(row.get("salesNumber") or 0),
                "orders": int(row.get("orderQuantity") or 0),
            }
            for row in rechecked_report_body.get("rows") or []
        }
        source_stable = all(source.get(sku, missing) == rechecked_source.get(sku, missing) for sku in mismatched_skus)
        report_stable = all(actual.get(sku, missing) == rechecked_report.get(sku, missing) for sku in mismatched_skus)
        source_lines = order_source_breakdown(rechecked_orders, rechecked_details, mismatched_skus)
        mismatches = {}
        for sku in mismatched_skus[:10]:
            by_order = defaultdict(lambda: {"quantity": 0, "lineQuantities": [], "groupSkuIds": set()})
            for line in source_lines.get(sku, []):
                order = by_order[line["orderNo"]]
                order["quantity"] += line["quantity"]
                order["lineQuantities"].append(line["quantity"])
                if line.get("groupSkuId"):
                    order["groupSkuIds"].add(line["groupSkuId"])
                for field in ("orderStatus", "payTime", "storeId"):
                    if line.get(field) is not None:
                        order[field] = line[field]
            order_summary = {
                order_no: {
                    **values,
                    "lineQuantities": values["lineQuantities"],
                    "groupSkuIds": sorted(values["groupSkuIds"]),
                }
                for order_no, values in by_order.items()
            }
            mismatches[sku] = {
                "report": actual.get(sku, missing),
                "orderSource": source.get(sku, missing),
                "reportRecheck": rechecked_report.get(sku, missing),
                "orderSourceRecheck": rechecked_source.get(sku, missing),
                "orderLinesByOrder": order_summary,
            }
        diagnostic = {
            "status": "STABLE_SOURCE_REPORT_MISMATCH" if source_stable and report_stable else "INCOMPLETE_DATA_CHANGED",
            "reportWindow": report_window,
            "storeIds": list(store_ids),
            "sourceStable": source_stable,
            "reportStable": report_stable,
            "mismatchSkuCount": len(mismatched_skus),
            "mismatches": mismatches,
        }
        print("SALES_VOLUME_RECONCILIATION_MISMATCH " + json.dumps(diagnostic, ensure_ascii=True, sort_keys=True))
        if not source_stable or not report_stable:
            pytest.fail("INCOMPLETE: source or report values changed during reconciliation; see diagnostic snapshot")
        assert not mismatched_skus, diagnostic


def test_multistore_sku_sales_against_order_items(
    report_query, report_window, sold_store_ids, sold_order_data, authenticated_http_client, api_base_url
):
    orders, details = sold_order_data
    _assert_sku_sales_match_order_source(
        report_query,
        report_window,
        sold_store_ids,
        orders,
        details,
        authenticated_http_client,
        api_base_url,
    )


def test_bundle_order_sample_is_available(
    sold_order_data, authenticated_http_client, api_base_url, report_window, report_query
):
    sampled_orders, details = sold_order_data
    api = SKUGroupAPI(authenticated_http_client, api_base_url)
    valid_orders = {str(order["orderNo"]) for order in sampled_orders if str(order.get("orderStatus")) != "6"}
    bundles = [
        row
        for order_no, rows in details.items()
        if str(order_no) in valid_orders
        for row in rows
        if isinstance(row.get("detail"), list) and row["detail"]
    ]
    if not bundles:
        available = api.list_page(page_num=1, page_size=100)
        api.assert_success(available)
        end = datetime.strptime(report_window[1], "%Y-%m-%d %H:%M:%S")
        for day in range(30):
            period_end = end - timedelta(days=day)
            window = (
                period_end.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
                period_end.strftime("%Y-%m-%d %H:%M:%S"),
            )
            try:
                candidate_orders, candidate_details = _fetch_order_data(
                    authenticated_http_client, api_base_url, window, []
                )
            except AssertionError as exc:
                if str(exc).startswith("No order sample or pagination incomplete"):
                    continue
                raise
            valid = {str(order["orderNo"]) for order in candidate_orders if str(order.get("orderStatus")) != "6"}
            bundles = [
                row
                for order_no, rows in candidate_details.items()
                if str(order_no) in valid
                for row in rows
                if isinstance(row.get("detail"), list) and row["detail"]
            ]
            if bundles:
                test_multistore_sku_sales_against_order_items(
                    report_query,
                    window,
                    [],
                    (candidate_orders, candidate_details),
                    authenticated_http_client,
                    api_base_url,
                )
                break
        if not bundles:
            pytest.fail(
                f"INCOMPLETE: {available['total']} combination SKUs, but no bundled order in the sampled period"
            )
    group_ids = {str(row.get("groupSkuId") or row.get("itemId") or "") for row in bundles}
    assert "" not in group_ids, "Bundle order rows have no group SKU identifier"
    for group_id in group_ids:
        page = 1
        matches = []
        while True:
            body = api.list_page(group_id, page_num=page, page_size=100)
            api.assert_success(body)
            rows = api.rows(body)
            matches.extend(row for row in rows if str(row.get("groupSkuId")) == group_id)
            if page * 100 >= body["total"]:
                break
            assert rows and page < 200, {"groupSkuId": group_id, "page": page}
            page += 1
        assert len(matches) == 1, {"groupSkuId": group_id, "matches": len(matches)}
        components = matches[0].get("omsSkuGroupItemVoList")
        assert components and all(row.get("itemId") and row.get("itemQty") is not None for row in components), group_id


def test_warehouse_expand_keeps_every_sku(report_query, report_window):
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    listing = report_query(DIMENSIONS["warehouse"], payload)
    assert listing.get("code") == 200, listing
    rows = listing.get("rows") or []
    assert rows and len(rows) == listing.get("total"), "No warehouse sample or pagination incomplete"
    ids = [row["itemId"] for row in rows]
    assert len(ids) == len(set(ids)), "Duplicate SKU in the warehouse listing"
    expanded = report_query("queryWarehouseSalesDimensionExpand", {**payload, "itemIds": ids})
    assert expanded.get("code") == 200, expanded
    details = expanded.get("data") or []
    stock = defaultdict(Decimal)
    warehouses = defaultdict(set)
    for detail in details:
        sku = str(detail.get("itemId"))
        stock[sku] += Decimal(str(detail.get("stockNumber") or 0))
        warehouses[sku].add(str(detail.get("warehouseName") or detail.get("locationId") or ""))
    multi = {sku: len(names) for sku, names in warehouses.items() if len(names) > 1}
    assert multi, "No SKU spans multiple warehouses; multi-warehouse completeness remains unverified"
    mismatched = {
        str(row["itemId"]): {"summary": row.get("stockNumber"), "expanded": str(stock[str(row["itemId"])])}
        for row in rows
        if stock[str(row["itemId"])] != Decimal(str(row.get("stockNumber") or 0))
    }
    assert not mismatched, {"message": "Expanded warehouse stock differs from the summary", "skus": mismatched}


@pytest.mark.slow
def test_category_distinct_orders_against_order_source(
    authenticated_http_client,
    api_base_url,
    report_query,
    report_window,
):
    base = {**build_filter(report_window), "pageNum": 1, "pageSize": 100}
    stores_response = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/base/store/queryPermissionStoreList",
        json={},
        timeout=(10, 90),
    )
    stores_response.raise_for_status()
    stores_body = stores_response.json()
    assert stores_body.get("code") == 200, stores_body
    stores = stores_body.get("data") or []
    assert stores, "No permitted stores"
    store_report = report_query(DIMENSIONS["store"], base)
    assert store_report.get("code") == 200 and store_report.get("rows"), "No store-dimension sales sample"
    expanded = report_query(
        "queryStoreSalesDimensionExpand",
        {
            **base,
            "itemIds": [row["itemId"] for row in store_report["rows"]],
        },
    )
    assert expanded.get("code") == 200, expanded
    sold_names = {row.get("storeName") for row in expanded.get("data") or [] if row.get("storeName")}
    candidates = [row for row in stores if row.get("storeName") in sold_names]
    assert candidates, "No sold stores matched to permitted store list"
    for store in candidates[:30]:
        ids = [str(store["id"])]
        payload = {**build_filter(report_window, store_ids=ids), "pageNum": 1, "pageSize": 500}
        sku_body = report_query(DIMENSIONS["sku"], payload)
        category_body = report_query(DIMENSIONS["category"], payload)
        assert sku_body.get("code") == category_body.get("code") == 200, (sku_body, category_body)
        sku_rows, categories = sku_body.get("rows") or [], category_body.get("rows") or []
        if not sku_rows or len(sku_rows) != sku_body.get("total") or len(sku_rows) > 500:
            continue
        if not categories or len(categories) != category_body.get("total"):
            continue
        orders, details = _fetch_order_data(authenticated_http_client, api_base_url, report_window, ids)
        category_ids = {str(row.get("classId")) for row in categories if row.get("classId")}
        sku_categories = {
            str(row["itemId"]): str(row["classId"]) if str(row.get("classId") or "") in category_ids else ""
            for row in sku_rows
        }
        has_multiple_skus = False
        for order in orders:
            if str(order.get("orderStatus")) == "6":
                continue
            groups = defaultdict(set)
            for item in order_item_rows(details.get(str(order["orderNo"])) or []):
                sku = str(item.get("itemId") or "")
                if sku in sku_categories and int(item.get("quantity") or 0) > 0:
                    groups[sku_categories[sku]].add(sku)
            if any(len(skus) > 1 for skus in groups.values()):
                has_multiple_skus = True
                break
        if not has_multiple_skus:
            continue
        expected = category_order_counts(orders, details, sku_categories)
        actual = {str(row.get("classId") or ""): int(row.get("orderNumber") or 0) for row in categories}
        assert actual == expected, {"storeId": ids[0], "report": actual, "orderSource": expected}
        return
    pytest.fail("No order with multiple SKUs in one category; distinct-count scenario incomplete")


def _assert_inventory_matches_report(authenticated_http_client, api_base_url, report_query, report_window, store_ids):
    payload = {**build_filter(report_window, store_ids=store_ids), "pageNum": 1, "pageSize": 500}
    report = report_query(DIMENSIONS["sku"], payload)
    assert report.get("code") == 200, report
    rows = report.get("rows") or []
    assert rows and len(rows) == report.get("total") <= 500, "No SKU sample or pagination incomplete"
    inventory = InventorySKUAPI(authenticated_http_client, api_base_url)
    missing = []
    mismatches = []
    for row in rows:
        sku = str(row["itemId"])
        matches = []
        page = 1
        while True:
            body = inventory.list_page(
                {
                    "beginCreateTime": "",
                    "endCreateTime": "",
                    "itemId": sku,
                    "pageNum": page,
                    "pageSize": 500,
                    "salesStatusList": [],
                    "searchMode": "3",
                }
            )
            table = inventory.assert_success(body)
            page_rows = inventory.rows(body)
            matches.extend(item for item in page_rows if str(item.get("itemId")) == sku)
            if matches or page * 500 >= table["total"]:
                break
            assert page_rows and page < 200, {"sku": sku, "page": page, "total": table["total"]}
            page += 1
        if not matches:
            missing.append(sku)
            continue
        stock = sum(int(item.get("stockQty") or 0) for item in matches)
        if stock != int(row.get("stockNum") or 0):
            mismatches.append({"sku": sku, "report": row.get("stockNum"), "inventory": stock})
    assert not missing, {"unverifiedInventorySku": missing}
    assert not mismatches, mismatches


def test_multistore_inventory_against_inventory_api(
    authenticated_http_client,
    api_base_url,
    report_query,
    report_window,
    sold_store_ids,
):
    _assert_inventory_matches_report(
        authenticated_http_client, api_base_url, report_query, report_window, sold_store_ids
    )


@pytest.mark.parametrize(
    "endpoint,extra",
    [
        ("exportOmsInventoryReportCurrentPage", {}),
        ("exportStoreSalesDimensionCurrentPage", {"storeManagerIds": [], "deptIdList": []}),
        ("exportWarehouseSalesDimensionCurrentPage", {"locationIds": []}),
        ("exportCountrySalesDimensionCurrentPage", {"countryCodes": []}),
        ("exportCategorySalesDimensionDetailReport", {"includeSkuDetail": 1}),
    ],
)
def test_multistore_realtime_export_matches_query(
    authenticated_http_client,
    api_base_url,
    report_query,
    report_window,
    sold_store_ids,
    endpoint,
    extra,
):
    payload = {**build_filter(report_window, store_ids=sold_store_ids), "pageNum": 1, "pageSize": 500}
    query = report_query(DIMENSIONS["sku"], payload)
    assert query.get("code") == 200, query
    rows = query.get("rows") or []
    assert rows and len(rows) == query.get("total") <= 500, "SKU sample missing or pagination incomplete"
    expected = group_sales_by_sku(rows)
    response = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/sales/report/" + endpoint,
        json={**payload, **extra},
        timeout=(10, 180),
    )
    response.raise_for_status()
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    actual = defaultdict(Decimal)
    for sheet in workbook:
        iterator = sheet.iter_rows(values_only=True)
        header = [str(value or "").replace(" ", "") for value in next(iterator)]
        sku_index = next(index for index, name in enumerate(header) if name in ("库存SKU", "SKU编码"))
        sale_index = header.index("销量")
        for row in iterator:
            if row[sku_index] not in (None, ""):
                actual[str(row[sku_index])] += Decimal(str(row[sale_index] or 0))
    assert dict(actual) == expected, {"query": expected, "export": dict(actual)}


def _read_sku_export(content):
    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    totals = defaultdict(Decimal)
    count = 0
    for sheet in workbook:
        iterator = sheet.iter_rows(values_only=True)
        header = [str(value or "").replace(" ", "") for value in next(iterator)]
        sku_index = next(index for index, name in enumerate(header) if name in ("库存SKU", "SKU编码"))
        sale_index = header.index("销量")
        for row in iterator:
            if row[sku_index] in (None, ""):
                continue
            totals[str(row[sku_index])] += Decimal(str(row[sale_index] or 0))
            count += 1
    return totals, count


def test_search_content_export_covers_all_rows(authenticated_http_client, api_base_url, report_query, report_window):
    root = api_base_url.rstrip("/")
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    query = report_query(DIMENSIONS["sku"], payload)
    assert query.get("code") == 200, query
    rows = query.get("rows") or []
    assert rows and len(rows) == query.get("total"), "Sample or pagination incomplete"
    expected = group_sales_by_sku(rows)
    total = int(query["total"])
    full = authenticated_http_client.post(
        root + "/oms-admin/sales/report/exportOmsInventoryReportV2",
        json=build_filter(report_window),
        timeout=(10, 300),
    )
    full.raise_for_status()
    actual, count = _read_sku_export(full.content)
    assert count == total, {"exportRows": count, "queryTotal": total, "message": "Search export is not full result"}
    assert dict(actual) == expected, {"query": expected, "export": dict(actual)}
    page_size = 50
    page = authenticated_http_client.post(
        root + "/oms-admin/sales/report/exportOmsInventoryReportCurrentPage",
        json={**build_filter(report_window), "pageNum": 1, "pageSize": page_size},
        timeout=(10, 300),
    )
    page.raise_for_status()
    _, page_count = _read_sku_export(page.content)
    assert page_count == page_size, {"currentPageExport": page_count, "expected": page_size}


def test_category_summary_export_matches_listing(authenticated_http_client, api_base_url, report_query, report_window):
    root = api_base_url.rstrip("/")
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    listing = report_query(DIMENSIONS["category"], payload)
    assert listing.get("code") == 200, listing
    rows = listing.get("rows") or []
    assert rows and len(rows) == listing.get("total"), "No category sample or pagination incomplete"
    expected = sorted(
        (
            Decimal(str(row.get("salesNumber") or 0)),
            Decimal(str(row.get("stockNumber") or 0)),
            int(row.get("orderNumber") or 0),
        )
        for row in rows
    )
    response = authenticated_http_client.post(
        root + "/oms-admin/sales/report/exportCategorySalesDimensionDetailReport",
        json=build_filter(report_window),
        timeout=(10, 300),
    )
    response.raise_for_status()
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    sheets = list(workbook)
    assert len(sheets) == 1, {"message": "Category summary export must not split per category", "sheets": len(sheets)}
    iterator = sheets[0].iter_rows(values_only=True)
    header = [str(value or "").replace(" ", "") for value in next(iterator)]
    sales_index = header.index("销量")
    stock_index = header.index("库存(汇总)")
    order_index = header.index("订单数")
    exported = sorted(
        (
            Decimal(str(row[sales_index] or 0)),
            Decimal(str(row[stock_index] or 0)),
            int(row[order_index] or 0),
        )
        for row in iterator
        if str(row[0] or "")
    )
    assert exported == expected, {"listing": expected, "export": exported}


def _assert_async_export_matches_query(session, api_base_url, report_query, payload, dimension, report_type):
    root = api_base_url.rstrip("/")
    before = report_query(DIMENSIONS["sku"], payload)
    assert before.get("code") == 200, before
    rows = before.get("rows") or []
    assert rows and len(rows) == before.get("total") <= 500, "No sample or incomplete pagination"
    expected = group_sales_by_sku(rows)
    conditions = {**payload, "exportReportType": report_type}
    if dimension == "store":
        conditions.update({"storeManagerIds": [], "deptIdList": []})
    if dimension == "category":
        conditions["includeSkuDetail"] = 1
    # Match the ERP's dimension-specific default name; the server appends its timestamp.
    task_name = build_export_task_name(dimension)

    def fetch_page(page_num, page_size):
        result = session.get(
            root + "/oms-admin/base/exportTask/list",
            params={"pageNum": page_num, "pageSize": page_size, "taskName": task_name},
            timeout=(10, 60),
        )
        result.raise_for_status()
        return result.json()

    previous_task_ids = {export_task_id(task) for task in list_export_tasks(fetch_page)}
    response = session.post(
        root + "/oms-admin/base/exportTask",
        json={
            "taskName": task_name,
            "taskType": "1",
            "exportType": "8",
            "exportColumn": "{}",
            "taskConditions": json.dumps(conditions, ensure_ascii=False),
        },
        timeout=(10, 90),
    )
    response.raise_for_status()
    assert response.json().get("code") == 200, response.text
    deadline = time.monotonic() + 300
    task = None
    while time.monotonic() < deadline:
        task = find_new_export_task(fetch_page, task_name, previous_task_ids)
        if task:
            if str(task.get("status")) == "1" and task.get("fileUrl"):
                break
            assert str(task.get("status")) != "2", task
        time.sleep(3)
    assert task and str(task.get("status")) == "1" and task.get("fileUrl"), {"task": task_name, "last": task}
    download = session.get(task["fileUrl"], timeout=(10, 180))
    download.raise_for_status()
    workbook = load_workbook(BytesIO(download.content), read_only=True, data_only=True)
    actual = defaultdict(Decimal)
    for sheet in workbook:
        iterator = sheet.iter_rows(values_only=True)
        header = [str(value or "").replace(" ", "") for value in next(iterator)]
        sku_index = next(index for index, name in enumerate(header) if name in ("库存SKU", "SKU编码"))
        sale_index = header.index("销量")
        for row in iterator:
            if row[sku_index] not in (None, ""):
                actual[str(row[sku_index])] += Decimal(str(row[sale_index] or 0))
    after = report_query(DIMENSIONS["sku"], payload)
    assert after.get("code") == 200 and len(after.get("rows") or []) == after.get("total") <= 500, after
    after_values = group_sales_by_sku(after["rows"])
    assert expected == after_values, {
        "message": "Source changed during async export; result inconclusive",
        "task": task_name,
    }
    assert dict(actual) == expected, {"task": task_name, "query": expected, "export": dict(actual)}


@pytest.mark.slow
@pytest.mark.parametrize(
    "dimension,report_type", [("sku", 1), ("store", 2), ("warehouse", 3), ("country", 4), ("category", 5)]
)
def test_multistore_async_export_matches_query(
    authenticated_http_client,
    api_base_url,
    report_query,
    report_window,
    sold_store_ids,
    dimension,
    report_type,
):
    payload = {**build_filter(report_window, store_ids=sold_store_ids), "pageNum": 1, "pageSize": 500}
    _assert_async_export_matches_query(
        authenticated_http_client, api_base_url, report_query, payload, dimension, report_type
    )


@pytest.mark.slow
def test_category_detail_export_over_20000_requires_task(authenticated_http_client, api_base_url, report_query):
    payload = {
        **build_filter(pay_range=("2026-04-10 00:00:00", "2026-10-10 00:00:00")),
        "pageNum": 1,
        "pageSize": 500,
    }
    categories = report_query(DIMENSIONS["category"], payload)
    assert categories.get("code") == 200, categories
    rows = categories.get("rows") or []
    assert rows and len(rows) == categories.get("total"), "Category sample missing or incomplete"
    detail_count = 0
    expected_sales = defaultdict(Decimal)
    for category in rows:
        detail = report_query("queryCategorySalesDimensionExpand", {**payload, "classIds": [category.get("classId")]})
        assert detail.get("code") == 200, detail
        details = detail.get("data") or []
        detail_count += len(details)
        assert all(item.get("itemId") for item in details), "Category details lack SKU identifiers"
        for sku, sales in group_sales_by_sku(details).items():
            expected_sales[sku] += sales
    assert detail_count > 20000, {"message": "Need more than 20000 details to test limit", "count": detail_count}
    assert detail_count > len(rows), {
        "message": "Detail count must exceed the category row count",
        "details": detail_count,
    }
    summary = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/sales/report/exportCategorySalesDimensionDetailReport",
        json=payload,
        timeout=(10, 180),
    )
    summary.raise_for_status()
    assert "json" not in str(summary.headers.get("content-type")), summary.text[:200]
    summary_book = load_workbook(BytesIO(summary.content), read_only=True, data_only=True)
    assert len(list(summary_book)) == 1, "Category summary export must stay a single sheet"
    response = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/sales/report/exportCategorySalesDimensionDetailReport",
        json={**payload, "includeSkuDetail": 1},
        timeout=(10, 180),
    )
    response.raise_for_status()
    body = response.json()
    assert body.get("code") != 200 and "20000" in str(body.get("msg", "")), body
    task_name = build_export_task_name("category")
    task_conditions = {**payload, "includeSkuDetail": 1, "exportReportType": 5}

    def fetch_page(page_num, page_size):
        result = authenticated_http_client.get(
            api_base_url.rstrip("/") + "/oms-admin/base/exportTask/list",
            params={"pageNum": page_num, "pageSize": page_size, "taskName": task_name},
            timeout=(10, 60),
        )
        result.raise_for_status()
        return result.json()

    previous_task_ids = {export_task_id(task) for task in list_export_tasks(fetch_page)}
    created = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/base/exportTask",
        json={
            "taskName": task_name,
            "taskType": "1",
            "exportType": "8",
            "exportColumn": "{}",
            "taskConditions": json.dumps(task_conditions, ensure_ascii=False),
        },
        timeout=(10, 90),
    )
    created.raise_for_status()
    assert created.json().get("code") == 200, created.text
    deadline = time.monotonic() + 600
    task = None
    while time.monotonic() < deadline:
        task = find_new_export_task(fetch_page, task_name, previous_task_ids)
        if task and str(task.get("status")) == "1" and task.get("fileUrl"):
            break
        assert not task or str(task.get("status")) != "2", task
        time.sleep(3)
    assert task and str(task.get("status")) == "1" and task.get("fileUrl"), {"marker": marker, "task": task}
    download = authenticated_http_client.get(task["fileUrl"], timeout=(10, 300))
    download.raise_for_status()
    exported_sales, exported_count = _read_sku_export(download.content)
    assert exported_count == detail_count, {"expectedDetails": detail_count, "exportedDetails": exported_count}
    assert dict(exported_sales) == dict(expected_sales), "Asynchronous export SKU sales differ from category details"


@pytest.mark.parametrize(
    "endpoint,extra",
    [
        ("exportStoreSalesDimensionCurrentPage", {"storeManagerIds": [], "deptIdList": []}),
        ("exportWarehouseSalesDimensionCurrentPage", {"locationIds": []}),
        ("exportCountrySalesDimensionCurrentPage", {"countryCodes": []}),
    ],
)
def test_detail_export_rows_follow_active_sort(authenticated_http_client, api_base_url, report_window, endpoint, extra):
    payload = {
        **build_filter(report_window),
        **extra,
        "pageNum": 1,
        "pageSize": 50,
        "sortField": "salesNumber",
        "sortOrder": "desc",
    }
    response = authenticated_http_client.post(
        api_base_url.rstrip("/") + "/oms-admin/sales/report/" + endpoint,
        json=payload,
        timeout=(10, 300),
    )
    response.raise_for_status()
    assert "json" not in str(response.headers.get("content-type")), response.text[:200]
    workbook = load_workbook(BytesIO(response.content), read_only=True, data_only=True)
    sheet = next(iter(workbook))
    iterator = sheet.iter_rows(values_only=True)
    header = [str(value or "").replace(" ", "") for value in next(iterator)]
    sales_index = header.index("销量")
    values = [float(row[sales_index]) for row in iterator if row[sales_index] not in (None, "")]
    assert len(values) >= 2, {"endpoint": endpoint, "message": "No detail rows to check order"}
    assert values == sorted(values, reverse=True), {"endpoint": endpoint, "values": values[:30]}

"""Role-sensitive checks for the merged sales volume report."""

import os
from datetime import datetime, timedelta

import pytest
import requests

from modules.auto_test.core.sales_volume_contract import DIMENSIONS, build_filter
from modules.auto_test.core.secret_provider import get_secret
from modules.auto_test.pages.login_page import LoginPage
from modules.auto_test.tests.test_sales_volume_regression import NoOrderSampleError

pytest_plugins = ("modules.auto_test.tests.test_sales_volume_regression",)


@pytest.mark.slow
def test_procurement_source_data(request, api_base_url, report_query, report_window, report_role):
    assert report_role == "procurement", "This reconciliation is only applicable to procurement"
    administrator_client = request.getfixturevalue("administrator_client")
    from modules.auto_test.tests.test_sales_volume_regression import (
        _assert_inventory_matches_report,
        _assert_sku_sales_match_order_source,
        _fetch_order_data,
    )

    orders, details, window = _find_daily_order_sample(
        report_window[1],
        lambda daily_window: _fetch_order_data(administrator_client, api_base_url, daily_window, []),
    )
    _assert_sku_sales_match_order_source(report_query, window, [], orders, details, administrator_client, api_base_url)
    _assert_inventory_matches_report(administrator_client, api_base_url, report_query, window, [])


def _find_daily_order_sample(end_time, fetch_order_data, days=30):
    end = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
    for day in range(days):
        current = end - timedelta(days=day)
        window = (
            current.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
            current.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            orders, details = fetch_order_data(window)
        except NoOrderSampleError:
            continue
        return orders, details, window
    raise AssertionError(f"No complete daily order sample in the last {days} days")


@pytest.fixture
def report_role():
    role = os.environ.get("SALES_VOLUME_ROLE")
    assert role in {
        "admin",
        "manager",
        "sales",
        "assistant",
        "procurement",
    }, "Set SALES_VOLUME_ROLE explicitly; role behavior must not be inferred from credentials"
    return role


def test_role_tabs(logged_in_page, ui_base_url, report_role):
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    page = logged_in_page
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    page.get_by_text("SKU维度", exact=True).first.wait_for(state="visible", timeout=30000)
    for tab in ("SKU维度", "发货仓库维度", "国家维度", "类目维度"):
        assert page.get_by_text(tab, exact=True).first.is_visible(), tab
    assert page.get_by_text("店铺维度", exact=True).count() == (0 if report_role == "procurement" else 1)


def test_role_store_permissions(authenticated_http_client, api_base_url, report_role, report_query, report_window):
    root = api_base_url.rstrip("/")
    response = authenticated_http_client.post(
        root + "/oms-admin/base/store/queryPermissionStoreList", json={}, timeout=(10, 90)
    )
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, body
    stores = body.get("data") or []
    if report_role == "procurement":
        assert not stores, stores
        return
    assert stores, "No permitted stores: cannot verify role data scope"
    allowed = {str(store.get("storeName")) for store in stores if store.get("storeName")}
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 50}
    listing = report_query("queryStoreSalesDimensionReport", payload)
    assert listing.get("code") == 200, listing
    rows = listing.get("rows") or []
    assert rows, "No sold SKU sample: role store scope remains unverified"
    detail = report_query("queryStoreSalesDimensionExpand", {**payload, "itemIds": [r["itemId"] for r in rows]})
    assert detail.get("code") == 200, detail
    details = detail.get("data") or []
    assert details, "No expanded store details: role scope remains unverified"
    unauthorized = {str(row["storeName"]) for row in details if row.get("storeName")} - allowed
    assert not unauthorized, sorted(unauthorized)


def test_creator_dropdown_available_after_refresh(logged_in_page, ui_base_url, report_role):
    root = ui_base_url.rstrip("/")
    if root.endswith("/index"):
        root = root[:-6]
    page = logged_in_page
    page.goto(root + "/product/productReport/salesVolume", wait_until="domcontentloaded")
    with page.expect_response(
        lambda response: "/system/dict/data/type/sys_user_username" in response.url, timeout=30000
    ) as captured:
        page.reload(wait_until="domcontentloaded")
    result = captured.value.json()
    page.get_by_text("SKU维度", exact=True).first.wait_for(state="visible", timeout=30000)
    field = (
        page.locator(".el-form-item:visible").filter(has=page.locator(".el-form-item__label", has_text="创建人")).first
    )
    field.locator(".keyword-select-trigger").click()
    popover = page.locator(".el-dialog:visible, .el-popper:visible, [role='dialog']:visible")
    popover.first.wait_for(state="visible", timeout=10000)
    assert result.get("code") == 200, {"role": report_role, "response": result}
    texts = [popover.nth(i).inner_text() for i in range(popover.count())]
    assert any("显示已停用用户" in text and len(text.splitlines()) > 1 for text in texts), {
        "role": report_role,
        "message": "Creator dropdown is empty or lacks the disabled-user control",
    }


def test_merged_report_menu_is_assigned(authenticated_http_client, api_base_url, report_role):
    response = authenticated_http_client.get(
        api_base_url.rstrip("/") + "/oms-admin/system/menu/getRouters", timeout=(10, 90)
    )
    response.raise_for_status()
    body = response.json()
    assert body.get("code") == 200, body

    def nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from nodes(child)

    menu_nodes = list(nodes(body.get("data") or []))
    fields = [str(node.get(key) or "") for node in menu_nodes for key in ("path", "component", "title")]
    titles = [str(node.get("meta", {}).get("title") or "") for node in menu_nodes if isinstance(node.get("meta"), dict)]
    assert any(
        "productReport/salesVolume" in field or field == "商品销量报表" for field in fields + titles
    ), report_role
    assert not any(
        "salesReport/salesReport" in field or field == "销售商品销量报表" for field in fields + titles
    ), report_role


@pytest.fixture
def administrator_client(browser):
    username, password = get_secret("ADMIN_USERNAME"), get_secret("ADMIN_PASSWORD")
    assert username and password, "Administrator credentials are required for cross-role verification"
    context = browser.new_context()
    page = context.new_page()
    captured = {}

    def capture(response):
        if "/auth/login" in response.url:
            captured["http_status"] = response.status
            captured["request_id"] = response.headers.get("x-request-id") or response.headers.get("x-trace-id")
            try:
                captured["body"] = response.json()
            except (ValueError, AttributeError):
                captured["body"] = {}
            try:
                captured["clientid"] = response.request.all_headers().get("clientid")
            except (AttributeError, TypeError):
                captured["clientid"] = None

    page.on("response", capture)
    session = requests.Session()
    try:
        login_succeeded = LoginPage(page).login(username, password)
        body = captured.get("body") or {}
        token_data = body.get("data") or {}
        token = token_data.get("token") or token_data.get("access_token")
        if not login_succeeded or not token or str(body.get("code")) != "200":
            raise AssertionError(
                {
                    "message": "Administrator login failed",
                    "page_login_succeeded": login_succeeded,
                    "http_status": captured.get("http_status"),
                    "app_code": body.get("code"),
                    "request_id": captured.get("request_id"),
                }
            )
        session.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        if captured.get("clientid"):
            session.headers["clientid"] = captured["clientid"]
        for cookie in context.cookies():
            session.cookies.set(
                cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/")
            )
        yield session
    finally:
        session.close()
        context.close()


@pytest.mark.slow
def test_role_denied_store_with_administrator_sold_sample(
    request,
    authenticated_http_client,
    api_base_url,
    report_role,
    report_window,
):
    if report_role in {"admin", "procurement"}:
        pytest.skip("Not applicable: administrator and procurement may view all data")
    administrator_client = request.getfixturevalue("administrator_client")
    root = api_base_url.rstrip("/")
    path = root + "/oms-admin/sales/report/"

    def post(session, url, payload):
        response = session.post(url, json=payload, timeout=(10, 180))
        response.raise_for_status()
        result = response.json()
        assert result.get("code") == 200, result
        return result

    own = post(authenticated_http_client, root + "/oms-admin/base/store/queryPermissionStoreList", {})
    allowed = {str(row["id"]) for row in own.get("data") or []}
    assert allowed, "No role store sample"
    admin = post(administrator_client, root + "/oms-admin/base/store/queryPermissionStoreList", {})
    candidates = [row for row in admin.get("data") or [] if str(row["id"]) not in allowed]
    assert candidates, "No store outside the role's permission range"
    base = {**build_filter(report_window), "pageNum": 1, "pageSize": 50}
    target = None
    for candidate in candidates[:100]:
        sample = post(administrator_client, path + "queryOmsInventoryNew", {**base, "storeIds": [str(candidate["id"])]})
        if float(sample.get("salesVolume") or 0) > 0:
            target = str(candidate["id"])
            break
    assert target, "No administrator-visible sold store outside role permissions; test incomplete"
    for endpoint in (
        "queryOmsInventoryNew",
        "queryWarehouseSalesDimensionReport",
        "queryCountrySalesDimensionReport",
        "queryCategorySalesDimensionReport",
    ):
        result = post(authenticated_http_client, path + endpoint, {**base, "storeIds": [target]})
        assert not result.get("rows") and not result.get("total"), {
            "role": report_role,
            "endpoint": endpoint,
            "storeId": target,
            "response": result,
        }


@pytest.mark.slow
@pytest.mark.parametrize("dimension,report_type", [("sku", 1), ("warehouse", 3), ("country", 4), ("category", 5)])
def test_procurement_async_export_matches_query(
    authenticated_http_client,
    login_token,
    refresh_authenticated_http_client,
    api_base_url,
    report_query,
    report_window,
    report_role,
    dimension,
    report_type,
):
    assert report_role == "procurement", "This export regression is only applicable to procurement"
    from modules.auto_test.tests.test_sales_volume_regression import _assert_async_export_matches_query

    payload = _procurement_async_export_payload(report_query, report_window, dimension)
    _assert_async_export_matches_query(
        authenticated_http_client,
        api_base_url,
        report_query,
        payload,
        dimension,
        report_type,
        login_token,
        refresh_authenticated_http_client,
    )


def _procurement_async_export_payload(report_query, report_window, dimension):
    windows = [report_window]
    if dimension == "category":
        end = datetime.strptime(report_window[1], "%Y-%m-%d %H:%M:%S")
        for days in (7, 1):
            start = (end.date() - timedelta(days=days - 1)).strftime("%Y-%m-%d 00:00:00")
            windows.append((start, report_window[1]))

    for pay_range in windows:
        payload = {**build_filter(pay_range=pay_range), "pageNum": 1, "pageSize": 500}
        if dimension != "category":
            return payload

        categories = report_query(DIMENSIONS["category"], payload)
        assert categories.get("code") == 200, categories
        rows = categories.get("rows") or []
        assert rows and len(rows) == categories.get("total") <= 500, {
            "message": "Procurement category sample missing or incomplete",
            "window": pay_range,
            "response": categories,
        }
        for category in rows:
            class_id = category.get("classId")
            if not class_id:
                continue
            detail = report_query("queryCategorySalesDimensionExpand", {**payload, "classIds": [class_id]})
            assert detail.get("code") == 200, detail
            detail_rows = detail.get("data") or []
            if detail_rows and len(detail_rows) <= 20000:
                return {**payload, "classIds": [class_id]}

    pytest.fail(
        "No procurement category sample under the 20000-row task limit in the selected 30-, 7-, or 1-day windows"
    )


@pytest.mark.slow
def test_procurement_data_matches_administrator(
    request, authenticated_http_client, api_base_url, report_role, report_window
):
    if report_role != "procurement":
        pytest.skip("Only applicable to procurement")
    administrator_client = request.getfixturevalue("administrator_client")
    payload = {**build_filter(report_window), "pageNum": 1, "pageSize": 500}
    url = api_base_url.rstrip("/") + "/oms-admin/sales/report/queryOmsInventoryNew"

    def get(session):
        response = session.post(url, json=payload, timeout=(10, 180))
        response.raise_for_status()
        body = response.json()
        assert body.get("code") == 200, body
        rows = body.get("rows") or []
        assert rows and len(rows) == body.get("total") <= 500, "No sample or incomplete pagination"
        return {str(row["itemId"]): (row.get("salesNumber"), row.get("stockNum")) for row in rows}

    before = get(administrator_client)
    procurement = get(authenticated_http_client)
    after = get(administrator_client)
    assert before == after, "Administrator data changed during cross-role comparison; test incomplete"
    assert procurement == before, {"administratorCount": len(before), "procurementCount": len(procurement)}

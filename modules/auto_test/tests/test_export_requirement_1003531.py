"""TEST/UAT regression for inventory and sales export requirement 1003531."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook
from playwright.sync_api import Page

from modules.auto_test.core.export_requirement_1003531 import (
    assert_complete_sku_pages,
    expected_page_rows,
    task_conditions,
)
from modules.auto_test.pages.export_task_page import ExportTaskPage
from modules.auto_test.pages.inventory_export_page import InventoryExportPage
from modules.auto_test.pages.inventory_sku_page import InventorySKUPage
from modules.auto_test.pages.sales_order_export_page import SalesOrderExportPage
from modules.auto_test.pages.sales_order_page import SalesOrderPage
from modules.trae_test.utils.runtime_paths import runtime_dir


def _app_root(config_manager) -> str:
    assert config_manager.env in {"test", "uat"}, config_manager.env
    return config_manager.base_url.rstrip("/").removesuffix("/index")


def _assert_target_environment(page: Page, config_manager) -> str:
    app_root = _app_root(config_manager)
    assert page.url.startswith(f"{app_root}/"), page.url
    return app_root


def _name(label: str) -> str:
    prefix = "CI_" if os.getenv("CI") or os.getenv("GITHUB_ACTIONS") else ""
    return f"{prefix}R1003531_{label}_{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _column(path: Path, index: int = 0) -> list[str]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        return [
            str(row[index])
            for sheet in book.worksheets
            for row in sheet.iter_rows(min_row=2, values_only=True)
            if len(row) > index and row[index] is not None
        ]
    finally:
        book.close()


def _download(page: Page, name: str) -> Path:
    output = Path(runtime_dir("downloads")) / f"{name}.xlsx"
    with page.expect_download(timeout=180000) as event:
        page.get_by_role("button", name="实时导出").click()
    event.value.save_as(str(output))
    return output


def _fixed_footer(page: Page, button) -> None:
    button.wait_for(state="visible")
    before = button.bounding_box()
    assert before is not None
    page.mouse.wheel(0, 900)
    after = button.bounding_box()
    assert after is not None and abs(after["y"] - before["y"]) <= 2
    page.set_viewport_size({"width": 1280, "height": 720})
    small = button.bounding_box()
    assert small is not None and 0 <= 720 - small["y"] - small["height"] <= 60


def _select_stopped_inventory(sku: InventorySKUPage) -> None:
    status = sku.page.locator(".el-select:visible").filter(has_text="在售").first
    status.locator(".el-select__wrapper").click()
    sku.page.locator(".el-select-dropdown__item:visible").filter(has_text="停售").first.click()
    active_tag = status.locator(".el-tag").filter(has_text="在售")
    if active_tag.count():
        active_tag.first.locator(".el-tag__close").click()
    sku.click_search()


def _large_inventory(page: Page, config_manager) -> tuple[InventorySKUPage, InventoryExportPage, int]:
    sku = InventorySKUPage(page)
    sku.navigate_to_search_page()
    _assert_target_environment(sku.page, config_manager)
    _select_stopped_inventory(sku)
    total = sku.get_result_count()
    assert total > 5000, f"Requirement 1003531 requires >5000 stopped SKUs, found {total}"
    sku.select_export_current_search()
    export = InventoryExportPage(sku.page)
    export.page.get_by_text(f"共 {total} 条").first.wait_for(timeout=90000)
    return sku, export, total


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
@pytest.mark.requirement("1003531")
def test_inventory_paged_current_search_and_fixed_footer(logged_in_page: Page, config_manager) -> None:
    _, export, total = _large_inventory(logged_in_page, config_manager)
    pages = expected_page_rows(total)
    assert len(pages) >= 2
    _fixed_footer(export.page, export.create_task_button())
    first = _column(_download(export.page, _name("sku_first")))
    assert len(first) == pages[0]
    export.export_page_number(len(pages))
    last = _column(_download(export.page, _name("sku_last")))
    assert len(last) == pages[-1]
    assert not set(first).intersection(last)


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
@pytest.mark.requirement("1003531")
def test_inventory_list_task_submits_filters(logged_in_page: Page, config_manager) -> None:
    sku = InventorySKUPage(logged_in_page)
    sku.navigate_to_search_page()
    _assert_target_environment(sku.page, config_manager)
    _select_stopped_inventory(sku)
    assert sku.get_result_count() > 0
    calls: list[str] = []
    payloads: list[dict] = []

    def capture(request) -> None:
        if request.resource_type not in {"xhr", "fetch"}:
            return
        if "queryItemId" in request.url:
            calls.append(request.url)
        if "/base/exportTask" in request.url:
            payloads.append(task_conditions(request.post_data_json))

    sku.page.on("request", capture)
    dialog = sku.open_list_export_task_dialog()
    dialog.locator(".el-select").first.click()
    sku.page.locator(".el-select-dropdown__item:visible").first.click()
    name = _name("sku_list")
    dialog.locator('input[placeholder="请输入任务名称"]').fill(name)
    with sku.page.expect_response(lambda response: "/base/exportTask" in response.url) as event:
        dialog.locator('button:has-text("确 定")').click()
    assert event.value.status == 200 and event.value.json().get("code") in (0, 200)
    assert not calls, "Inventory list queried SKU IDs before task creation"
    assert payloads and payloads[0].get("salesStatusList") == ["2"]
    assert "queryItemId" not in payloads[0]
    print(f"Created {config_manager.env} inventory export task: {name}")


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.slow
@pytest.mark.p1
@pytest.mark.requirement("1003531")
def test_inventory_all_pages_equal_async_task(logged_in_page: Page, config_manager) -> None:
    _, export, total = _large_inventory(logged_in_page, config_manager)
    pages = []
    for number in range(1, len(expected_page_rows(total)) + 1):
        if number > 1:
            export.export_page_number(number)
        pages.append(_column(_download(export.page, _name(f"sku_p{number}"))))
    name = _name("sku_full")
    export.create_task_button().click()
    dialog = export.page.locator(".el-dialog:visible")
    dialog.locator('input[placeholder="请输入任务名称"]').fill(name)
    with export.page.expect_response(lambda response: "/base/exportTask" in response.url) as event:
        dialog.locator('button:has-text("确定")').click()
    assert event.value.status == 200 and event.value.json().get("code") in (0, 200)
    logged_in_page.goto(f"{_app_root(config_manager)}/system/tool/exportTask")
    task_page = ExportTaskPage(logged_in_page)
    task_file = task_page.download(name.split("_sku_full_")[-1], Path(runtime_dir("downloads")) / f"{name}_task.xlsx")
    assert_complete_sku_pages(pages, _column(task_file), total)


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
@pytest.mark.requirement("1003531")
def test_sales_current_search_realtime_and_fixed_footer(logged_in_page: Page, config_manager) -> None:
    sales = SalesOrderPage(logged_in_page)
    sales.navigate_to("sales/order/saleOrder")
    _assert_target_environment(logged_in_page, config_manager)
    logged_in_page.get_by_text("WMS取消发货", exact=False).first.click()
    logged_in_page.locator('button:visible:has-text("搜索")').first.click()
    total = int(re.findall(r"共\s*(\d+)\s*条", logged_in_page.locator("body").inner_text())[-1])
    assert 0 < total < 5000
    sales.select_export_current_search()
    target = [p for p in logged_in_page.context.pages if "exportPage" in p.url][-1]
    target.get_by_text(f"共 {total} 条").first.wait_for(timeout=90000)
    export = SalesOrderExportPage(target)
    _fixed_footer(target, export.create_task_button())
    values = _column(_download(target, _name("sales_realtime")))
    assert len(values) == total


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.slow
@pytest.mark.p1
@pytest.mark.requirement("1003531")
def test_sales_current_search_async_equals_realtime(logged_in_page: Page, config_manager) -> None:
    sales = SalesOrderPage(logged_in_page)
    sales.navigate_to("sales/order/saleOrder")
    app_root = _assert_target_environment(logged_in_page, config_manager)
    logged_in_page.get_by_text("WMS取消发货", exact=False).first.click()
    logged_in_page.locator('button:visible:has-text("搜索")').first.click()
    total = int(re.findall(r"共\s*(\d+)\s*条", logged_in_page.locator("body").inner_text())[-1])
    assert 0 < total < 5000
    sales.select_export_current_search()
    target = [p for p in logged_in_page.context.pages if "exportPage" in p.url][-1]
    target.get_by_text(f"共 {total} 条").first.wait_for(timeout=90000)
    export = SalesOrderExportPage(target)
    values = _column(_download(target, _name("sales_realtime_slow")))
    assert len(values) == total
    name = _name("sales_page")
    export.create_task_button().click()
    dialog = target.locator(".el-dialog:visible")
    dialog.locator('input[placeholder="请输入任务名称"]').fill(name)
    with target.expect_response(lambda response: "/base/exportTask" in response.url) as event:
        dialog.locator('button:has-text("确定")').click()
    assert event.value.status == 200 and event.value.json().get("code") in (0, 200)
    task_browser_page = logged_in_page.context.new_page()
    task_browser_page.goto(f"{app_root}/system/tool/exportTask")
    output = ExportTaskPage(task_browser_page).download(
        name[-14:], Path(runtime_dir("downloads")) / f"{name}_task.xlsx"
    )
    assert _column(output) == values


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
@pytest.mark.requirement("1003531")
def test_sales_list_task_submits_filters_without_ids(logged_in_page: Page, config_manager) -> None:
    sales = SalesOrderPage(logged_in_page)
    sales.navigate_to("sales/order/saleOrder")
    _assert_target_environment(logged_in_page, config_manager)
    logged_in_page.get_by_text("待付款", exact=False).first.click()
    logged_in_page.locator('button:visible:has-text("搜索")').first.click()
    calls = []
    payloads = []

    def capture(request) -> None:
        if request.resource_type not in {"xhr", "fetch"}:
            return
        if "/sales/order/orderNoList" in request.url:
            calls.append(request.url)
        if "/base/exportTask" in request.url:
            payloads.append(task_conditions(request.post_data_json))

    logged_in_page.on("request", capture)
    sales.click_export_button()
    logged_in_page.locator('.el-dropdown-menu__item:visible:has-text("创建导出任务")').first.click()
    dialog = logged_in_page.locator(".el-dialog:visible")
    dialog.wait_for(timeout=60000)
    dialog.locator(".el-select").first.locator(".el-select__wrapper").click()
    templates = logged_in_page.locator(".el-select-dropdown__item:visible:not(.is-disabled)")
    templates.first.wait_for(timeout=30000)
    templates.first.click(force=True)
    name = _name("sales_list")
    dialog.locator('input[placeholder="请输入任务名称"]').fill(name)
    with logged_in_page.expect_response(lambda response: "/base/exportTask" in response.url) as event:
        dialog.locator('button:has-text("确 定")').click()
    assert event.value.status == 200 and event.value.json().get("code") in (0, 200)
    print(f"Sales task request: prefetch_count={len(calls)}, condition_keys={sorted(payloads[0]) if payloads else []}")
    assert payloads, "Sales list task request was not captured"
    assert not calls, "Sales list queried order numbers before task creation"
    assert "orderNos" not in payloads[0], "Sales list submitted order numbers instead of filters"

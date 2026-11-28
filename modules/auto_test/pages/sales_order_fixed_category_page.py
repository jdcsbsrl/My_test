"""Sales-order fixed-category search controls for requirement 1003845."""

from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect


class SalesOrderFixedCategoryPage:
    """Read-only UI driver for the sales-order fixed-category filters."""

    ROUTE = "sales/order/saleOrder"

    def __init__(self, page: Page, base_url: str) -> None:
        if not base_url.startswith("https://erptest.dayoneerp.com/oms-ui"):
            raise ValueError("需求1003845 UI回归仅允许指定的test环境")
        self.page = page
        self.url = f"{base_url.rstrip('/').removesuffix('/index')}/{self.ROUTE}"

    def open(self) -> None:
        self.page.goto(self.url, wait_until="domcontentloaded", timeout=60000)
        expect(self.page.get_by_text("销售订单", exact=True).first).to_be_visible(timeout=60000)
        initial = self.page.locator(".el-select").filter(has_text="固定分类").first
        expect(initial).to_be_visible(timeout=60000)
        initial.evaluate("element => element.dataset.testR1003845 = 'fixed-category'")

    def fixed_category_select(self) -> Locator:
        return self.page.locator('[data-test-r1003845="fixed-category"]')

    def open_fixed_category(self) -> Locator:
        dropdown = (
            self.page.locator(".el-select-dropdown:visible")
            .filter(has=self.page.locator(".custom-option:visible"))
            .first
        )
        if not dropdown.is_visible():
            self.fixed_category_select().locator(".el-select__wrapper").click()
        expect(dropdown).to_be_visible()
        return dropdown

    def visible_dropdown_text(self) -> str:
        return self.open_fixed_category().inner_text()

    def filter_row(self, label: str) -> Locator:
        dropdown = self.open_fixed_category()
        checkbox = dropdown.get_by_role("checkbox", name=label, exact=True)
        return checkbox.locator(
            "xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), " "' custom-option ')][1]"
        )

    def enable_filter(self, label: str) -> Locator:
        row = self.filter_row(label)
        checkbox = row.locator('input[type="checkbox"]')
        row.scroll_into_view_if_needed()
        row.locator("label.el-checkbox").click(force=True)
        expect(checkbox).to_be_checked()
        inner = row.locator(".inner-select")
        expect(inner.locator(".el-select__wrapper")).not_to_have_class(re.compile(r"\bis-disabled\b"))
        return inner

    def option_values(self, label: str) -> list[str]:
        inner = self.enable_filter(label)
        options = self._open_inner_options(inner)
        expect(options.first).to_be_visible()
        values = [value.strip() for value in options.all_inner_texts() if value.strip()]
        self.page.keyboard.press("Escape")
        return values

    def select_filter(self, label: str, option: str) -> None:
        self.open_fixed_category()
        row = self.filter_row(label)
        checkbox = row.locator('input[type="checkbox"]')
        if not checkbox.is_checked():
            inner = self.enable_filter(label)
        else:
            inner = row.locator(".inner-select")
        options = self._open_inner_options(inner)
        target = options.filter(has=self.page.get_by_text(option, exact=True)).first
        expect(target).to_be_visible()
        target.click()
        self.page.keyboard.press("Escape")

    def _open_inner_options(self, inner: Locator) -> Locator:
        combobox = inner.locator('input[role="combobox"]')
        controls = combobox.get_attribute("aria-controls")
        assert controls, "固定分类内层下拉框缺少aria-controls"
        inner.locator(".el-select__wrapper").click()
        listbox = self.page.locator(f"#{controls}")
        expect(listbox).to_be_visible()
        return listbox.locator(".el-select-dropdown__item")

    def search_responses(self, select_type: str | None, select_flag: str | None = None):
        def is_expected_search(response) -> bool:
            if "/sales/order/batchListNew" not in response.url:
                return False
            body = response.request.post_data_json
            if not isinstance(body, dict):
                return False
            conditions = body.get("fixedClassId")
            if not isinstance(conditions, list) or len(conditions) != 1:
                return False
            condition = conditions[0]
            return (select_type is None or condition.get("selectType") == select_type) and (
                select_flag is None or condition.get("selectFlag") == select_flag
            )

        with self.page.expect_response(
            is_expected_search,
            timeout=60000,
        ) as order_event:
            self.search_button().click()
        order_response = order_event.value
        assert order_response.status == 200, f"订单搜索HTTP状态异常: {order_response.status}"
        order_payload = order_response.json()
        assert order_payload.get("code") == 200, f"订单搜索业务响应异常: {order_payload}"
        order_data = order_payload.get("data")
        assert isinstance(order_data, dict), f"订单搜索缺少data对象: {order_payload}"
        rows = order_data.get("tableDataInfo", {}).get("rows", [])
        order_numbers = [str(row["orderNo"]) for row in rows]
        api_root = order_response.url.split("/oms-admin/", maxsplit=1)[0]
        request_headers = {
            key: value
            for key, value in order_response.request.headers.items()
            if key.lower() not in {"content-length", "host"}
        }
        item_response = self.page.context.request.post(
            f"{api_root}/oms-admin/sales/orderItem/queryAllList",
            data={"orderNoList": order_numbers},
            headers=request_headers,
            timeout=60000,
        )
        assert item_response.status == 200, f"订单明细HTTP状态异常: {item_response.status}"
        return order_response, item_response

    @staticmethod
    def fixed_condition(response) -> dict[str, str]:
        body = response.request.post_data_json
        conditions = body.get("fixedClassId", []) if isinstance(body, dict) else []
        assert len(conditions) == 1, f"预期仅提交一个固定分类，实际: {conditions}"
        return conditions[0]

    def search_button(self) -> Locator:
        return self.page.get_by_role("button", name="搜索", exact=True).first

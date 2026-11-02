"""Read-only country search controls on the test customer quotation list."""

from __future__ import annotations

from playwright.sync_api import Page, expect

PATH = "/oms-ui/sales/customerQuotes/customerQuotation"


class CustomerQuotationCountrySearchPage:
    def __init__(self, page: Page, base_url: str) -> None:
        if not base_url.startswith("https://erptest.dayoneerp.com/oms-ui"):
            raise ValueError("报价国家 UI 回归仅允许指定的 test 环境")
        self.page = page
        self.url = "https://erptest.dayoneerp.com" + PATH

    def open(self) -> None:
        self.page.goto(self.url)
        self.page.wait_for_load_state("networkidle", timeout=15000)
        expect(self.page.get_by_text("报价国家", exact=True)).to_be_visible()
        expect(self.page.get_by_placeholder("请选择报价国家").first).to_be_visible()
        expect(self.page.locator(".el-table__body-wrapper tr").first).to_be_visible()

    def open_country_picker(self) -> None:
        picker = self.page.locator(".el-cascader").filter(has=self.page.get_by_placeholder("请选择报价国家").first)
        panel = self.page.locator(".el-cascader-panel")
        if not panel.is_visible():
            picker.click()
        expect(panel).to_be_visible()

    def select_path(self, continent: str, country: str | None = None) -> None:
        self.open_country_picker()
        panel = self.page.locator(".el-cascader-panel")
        continent_node = panel.locator(".el-cascader-node", has_text=continent).first
        expect(continent_node).to_be_visible()
        if country is None:
            continent_node.locator(".el-checkbox").click()
        else:
            continent_node.hover()
            country_node = panel.locator(".el-cascader-menu").last.locator(".el-cascader-node", has_text=country).first
            expect(country_node).to_be_visible()
            country_node.locator(".el-checkbox").click()
        self.page.keyboard.press("Escape")

    def search(self) -> None:
        self.page.get_by_role("button", name="搜索", exact=True).click()
        expect(self.page.locator(".el-table__body-wrapper")).to_be_visible()
        self.page.wait_for_load_state("networkidle", timeout=15000)
        self.page.wait_for_timeout(900)

    def customer_number(self, value: str) -> None:
        self.page.get_by_placeholder("客户编号").fill(value)

    def reset(self) -> None:
        self.page.get_by_role("button", name="重置", exact=True).click()

    def visible_customer_numbers(self) -> list[str]:
        return self.page.locator(".el-table__body-wrapper tr").evaluate_all(
            "rows => rows.map(row => row.innerText).filter(text => text.trim())"
        )

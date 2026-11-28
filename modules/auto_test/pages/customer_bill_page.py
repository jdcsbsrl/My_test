"""Read-only customer-bill exchange-rate tooltip observations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

from modules.auto_test.pages.base_page import BasePage

CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "HKD": "HK$",
    "MOP": "MOP$",
    "CNY": "¥",
}


@dataclass(frozen=True)
class CustomerBillRateTooltip:
    """Parsed exchange-rate tooltip for one visible customer bill."""

    bill_currency: str
    bill_amount: Decimal
    currencies: tuple[str, ...]
    exchange_rates: dict[str, Decimal]
    platform_amounts: dict[str, dict[str, Decimal]]

    def rate(self, currency: str) -> Decimal:
        return self.exchange_rates[currency.upper()]

    def platform_amount(self, platform: str, currency: str) -> Decimal:
        return self.platform_amounts[platform.upper()][currency.upper()]


class CustomerBillPage(BasePage):
    """Read-only access to the customer-bill list and amount tooltip."""

    PATH = "/oms-ui/sales/customer/customerBill"
    TABLE_ROWS = ".el-table__body-wrapper tbody tr"
    TOOLTIP = ".receivable-bill-amount-tooltip:visible"
    TABS = {"全部", "订单账单"}
    AMOUNT_COLUMNS = {"账单总额", "客户未付"}

    def __init__(self, page: Page, *, config=None) -> None:
        super().__init__(page, config=config)

    def open(self, tab: str = "订单账单") -> None:
        if getattr(self.config, "env", None) != "test":
            raise ValueError("需求1003647只允许在 test 环境执行")
        if tab not in self.TABS:
            raise ValueError(f"不支持的客户账单页签: {tab}")
        origin = urlsplit(self.base_url)
        if origin.scheme != "https" or not origin.netloc:
            raise ValueError("客户账单只允许在已配置的 HTTPS test 环境访问")
        self.navigate_to(f"{origin.scheme}://{origin.netloc}{self.PATH}")
        self.wait_for_business_ready(
            [self.TABLE_ROWS],
            page_name="customer_bill",
            required_selectors=[".el-table__header-wrapper"],
        )
        self.assert_identity()
        self.page.get_by_text(tab, exact=True).first.click()
        self.wait_for_loading_complete()
        self.page.locator(self.TABLE_ROWS).first.wait_for(state="visible", timeout=30000)
        self.active_tab = tab

    def assert_identity(self) -> None:
        if urlsplit(self.page.url).path != self.PATH:
            raise AssertionError("当前页面不是客户账单页面")
        expect(self.page).to_have_title("ERP::客户账单")
        expect(self.page.get_by_text("订单账单", exact=True).first).to_be_visible()

    def hover_first_bill(self, currency: str, column: str = "账单总额") -> CustomerBillRateTooltip:
        """Hover one amount field for ``currency`` and parse its tooltip."""

        self.assert_identity()
        if column not in self.AMOUNT_COLUMNS:
            raise ValueError(f"不支持的悬浮金额列: {column}")
        code = currency.upper()
        symbol = CURRENCY_SYMBOLS.get(code)
        if symbol is None:
            raise ValueError(f"不支持的账单币种: {currency}")

        target_column = self._column_index(column)
        total_column = self._column_index("账单总额")
        rows = self.page.locator(self.TABLE_ROWS)
        for index in range(rows.count()):
            row = rows.nth(index)
            total_trigger = row.locator(f"td:nth-child({total_column}) .el-tooltip__trigger").first
            if total_trigger.count() == 0 or not total_trigger.inner_text().strip().startswith(symbol):
                continue
            cell = row.locator(f"td:nth-child({target_column})")
            trigger = cell.locator(".el-tooltip__trigger")
            if trigger.count() == 0:
                continue
            amount_text = trigger.first.inner_text().strip()
            trigger = trigger.first
            self.page.mouse.move(1, 1)
            for visible_tooltip in self.page.locator(self.TOOLTIP).all():
                try:
                    visible_tooltip.wait_for(state="hidden", timeout=2000)
                except Exception:
                    pass
            trigger.hover()
            described_by = trigger.get_attribute("aria-describedby")
            tooltip = (
                self.page.locator(f"[id='{described_by}']:visible")
                if described_by
                else self.page.locator(self.TOOLTIP).last
            )
            tooltip.wait_for(state="visible", timeout=5000)
            return self._parse_tooltip(code, amount_text, tooltip)

        pytest.fail(f"BLOCKED: {getattr(self, 'active_tab', '当前')}页签的{column}列没有可见的 {code} 账单样本")

    def _column_index(self, column: str) -> int:
        aliases = {"账单总额": {"账单总额", "账单总金额"}, "客户未付": {"客户未付"}}
        expected = aliases[column]
        headers = self.page.locator(".el-table__header-wrapper th").all_inner_texts()
        for index, text in enumerate(headers, start=1):
            labels = {part.strip() for part in text.splitlines() if part.strip()}
            if labels.intersection(expected):
                return index
        raise AssertionError(f"{getattr(self, 'active_tab', '当前')}页签缺少金额列: {column}")

    @staticmethod
    def _parse_decimal(value: str) -> Decimal:
        cleaned = value.strip().replace(",", "")
        for symbol in sorted(CURRENCY_SYMBOLS.values(), key=len, reverse=True):
            if cleaned.startswith(symbol):
                cleaned = cleaned[len(symbol) :]
                break
        return Decimal(cleaned)

    @classmethod
    def _parse_tooltip(cls, bill_currency: str, amount_text: str, tooltip) -> CustomerBillRateTooltip:
        table = tooltip.locator("table")
        headers = [" ".join(text.split()) for text in table.locator("thead th").all_inner_texts()]
        currencies = tuple(text.rsplit(" ", 1)[-1].upper() for text in headers[1:])
        if not currencies:
            raise AssertionError("汇率弹窗没有币种表头")

        body_rows = table.locator("tbody tr")
        parsed_rows: dict[str, dict[str, Decimal]] = {}
        for row_index in range(body_rows.count()):
            values = [" ".join(text.split()) for text in body_rows.nth(row_index).locator("td").all_inner_texts()]
            if len(values) != len(currencies) + 1:
                raise AssertionError(f"汇率弹窗行列数不一致: {values!r}")
            parsed_rows[values[0].upper()] = {
                code: cls._parse_decimal(value) for code, value in zip(currencies, values[1:], strict=True)
            }

        exchange_rates = parsed_rows.pop("EXCHANGE RATE", None)
        if exchange_rates is None:
            raise AssertionError("汇率弹窗缺少 Exchange Rate 行")
        return CustomerBillRateTooltip(
            bill_currency=bill_currency,
            bill_amount=cls._parse_decimal(amount_text),
            currencies=currencies,
            exchange_rates=exchange_rates,
            platform_amounts=parsed_rows,
        )

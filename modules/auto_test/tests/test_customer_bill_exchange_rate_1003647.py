"""Requirement 1003647: customer-bill exchange-rate display direction."""

from __future__ import annotations

from decimal import Decimal

import pytest

from modules.auto_test.api.quotation_rate_api import QuotationRateAPI
from modules.auto_test.pages.customer_bill_page import CustomerBillPage

RECIPROCAL_TOLERANCE = Decimal("0.03")
UI_SCENARIOS = (
    pytest.param("订单账单", "账单总额", id="order-total"),
    pytest.param("订单账单", "客户未付", id="order-unpaid"),
    pytest.param("全部", "账单总额", id="all-total"),
    pytest.param("全部", "客户未付", id="all-unpaid"),
)


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003647")
@pytest.mark.parametrize("tab,column", UI_SCENARIOS)
def test_customer_bill_rate_row_uses_the_bill_currency_as_one(
    logged_in_page, config_manager, tab: str, column: str
) -> None:
    """EUR and USD bills must each display their own currency as the unit rate."""

    assert config_manager.env == "test", "需求1003647只允许在 test 环境执行"
    bill_page = CustomerBillPage(logged_in_page, config=config_manager)

    bill_page.open(tab)
    euro_tooltip = bill_page.hover_first_bill("EUR", column)
    bill_page.open(tab)
    usd_tooltip = bill_page.hover_first_bill("USD", column)

    assert euro_tooltip.rate("EUR") == Decimal("1"), "欧元账单必须显示 1 EUR"
    assert euro_tooltip.rate("USD") > Decimal("1"), "欧元账单的美元汇率应显示为 1 欧元对应的美元数"
    assert usd_tooltip.rate("USD") == Decimal("1"), "美元账单必须显示 1 USD"
    assert Decimal("0") < usd_tooltip.rate("EUR") < Decimal("1"), "美元账单的欧元汇率应小于 1"
    assert abs(euro_tooltip.rate("USD") * usd_tooltip.rate("EUR") - Decimal("1")) <= RECIPROCAL_TOLERANCE


@pytest.mark.ui
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003647")
@pytest.mark.parametrize("tab,column", UI_SCENARIOS)
def test_customer_bill_platform_amounts_remain_unchanged(logged_in_page, config_manager, tab: str, column: str) -> None:
    """The requirement explicitly excludes the lower platform conversion rows."""

    assert config_manager.env == "test", "需求1003647只允许在 test 环境执行"
    bill_page = CustomerBillPage(logged_in_page, config=config_manager)
    tooltips = []
    for currency in ("EUR", "USD"):
        bill_page.open(tab)
        tooltips.append(bill_page.hover_first_bill(currency, column))

    for tooltip in tooltips:
        for platform in ("WISE", "AIRWALLEX", "PINGPONG"):
            assert (
                tooltip.platform_amount(platform, tooltip.bill_currency) == tooltip.bill_amount
            ), f"{platform} 的账单币种金额不应因汇率展示修复而变化"


@pytest.mark.api
@pytest.mark.regression
@pytest.mark.p0
@pytest.mark.requirement("1003647")
def test_current_eur_usd_rates_are_reciprocal(authenticated_http_client, api_base_url) -> None:
    """The current-day API is an oracle only for bills whose selected rate date is today."""

    rate_api = QuotationRateAPI(authenticated_http_client, api_base_url)
    eur_to_usd = rate_api.convert(transaction_currency="EUR", base_currency="USD")
    usd_to_eur = rate_api.convert(transaction_currency="USD", base_currency="EUR")

    assert eur_to_usd.transaction_currency == "EUR" and eur_to_usd.base_currency == "USD"
    assert usd_to_eur.transaction_currency == "USD" and usd_to_eur.base_currency == "EUR"
    assert eur_to_usd.exchange_rate > Decimal("1")
    assert Decimal("0") < usd_to_eur.exchange_rate < Decimal("1")
    assert abs(eur_to_usd.exchange_rate * usd_to_eur.exchange_rate - Decimal("1")) <= Decimal("0.001")

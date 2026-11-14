from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from modules.auto_test.api.quotation_rate_api import QuotationRateAPI, select_bill_rate_lookup
from modules.auto_test.pages.customer_bill_page import CustomerBillPage


def test_parse_current_rate_response_preserves_direction() -> None:
    conversion = QuotationRateAPI.parse_conversion(
        {
            "code": 200,
            "msg": "操作成功",
            "data": {
                "baseCurrency": "USD",
                "transactionCurrency": "EUR",
                "amount": 1,
                "transactionAmount": "0.8774",
                "exchangeRate": "1.1397",
            },
        }
    )
    assert conversion.transaction_currency == "EUR"
    assert conversion.base_currency == "USD"
    assert conversion.exchange_rate == Decimal("1.1397")
    assert conversion.transaction_amount == Decimal("0.8774")


def test_parse_current_rate_response_rejects_missing_fields() -> None:
    with pytest.raises(AssertionError, match="缺少字段"):
        QuotationRateAPI.parse_conversion({"code": 200, "data": {"baseCurrency": "USD"}})


@pytest.mark.parametrize(
    "raw, expected",
    [("€15.50", Decimal("15.50")), ("$-225", Decimal("-225")), ("1,234.56", Decimal("1234.56"))],
)
def test_customer_bill_decimal_parser_handles_currency_amounts(raw: str, expected: Decimal) -> None:
    assert CustomerBillPage._parse_decimal(raw) == expected


def test_customer_bill_page_rejects_non_test_environment() -> None:
    page = Mock()
    config = Mock(base_url="https://example.com/oms-ui", env="uat")
    with patch("modules.auto_test.pages.base_page.SelfHealingLocator"):
        customer_bill = CustomerBillPage(page, config=config)
    with pytest.raises(ValueError, match="test 环境"):
        customer_bill.open()
    page.goto.assert_not_called()


@pytest.mark.parametrize(
    "snapshot, receivable, general, today, expected_snapshot, expected_date",
    [
        (Decimal("1.20"), date(2026, 10, 1), date(2026, 9, 30), date(2026, 11, 4), True, None),
        (None, date(2026, 10, 1), date(2026, 9, 30), date(2026, 11, 4), False, date(2026, 10, 1)),
        (None, date(2026, 12, 1), date(2026, 10, 26), date(2026, 11, 4), False, date(2026, 10, 26)),
        (None, None, None, date(2026, 11, 4), False, date(2026, 11, 4)),
    ],
)
def test_select_bill_rate_lookup_follows_snapshot_and_date_precedence(
    snapshot, receivable, general, today, expected_snapshot, expected_date
) -> None:
    result = select_bill_rate_lookup(
        approval_receipt_rate=snapshot,
        receivable_date=receivable,
        general_date=general,
        today=today,
    )
    assert result.use_snapshot is expected_snapshot
    assert result.rate_date == expected_date

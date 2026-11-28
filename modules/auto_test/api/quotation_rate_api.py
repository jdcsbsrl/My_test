"""Read-only client for the current-day quotation-rate conversion endpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import requests


@dataclass(frozen=True)
class QuotationRateConversion:
    base_currency: str
    transaction_currency: str
    amount: Decimal
    transaction_amount: Decimal
    exchange_rate: Decimal


@dataclass(frozen=True)
class BillRateLookup:
    """Rate source selected from the customer-bill snapshot/date contract."""

    use_snapshot: bool
    rate_date: date | None


def select_bill_rate_lookup(
    *,
    approval_receipt_rate: Decimal | None,
    receivable_date: date | None,
    general_date: date | None,
    today: date,
) -> BillRateLookup:
    """Select the snapshot or historical date without calling the current-day API."""

    if approval_receipt_rate is not None:
        return BillRateLookup(use_snapshot=True, rate_date=None)
    if receivable_date is not None and today >= receivable_date:
        return BillRateLookup(use_snapshot=False, rate_date=receivable_date)
    return BillRateLookup(use_snapshot=False, rate_date=general_date or today)


class QuotationRateAPI:
    """Query current-day rates without mutating ERP data."""

    PATH = "/oms-admin/finance/quotationRate/exchangeRateConversion"
    REQUEST_TIMEOUT = (10, 60)

    def __init__(self, session: requests.Session, api_base_url: str) -> None:
        self.session = session
        self.base_url = api_base_url.rstrip("/")

    def convert(
        self,
        *,
        transaction_currency: str,
        base_currency: str,
        amount: Decimal = Decimal("1"),
    ) -> QuotationRateConversion:
        if not amount.is_finite():
            raise ValueError("amount must be a finite Decimal")

        payload = json.dumps(
            {
                "transactionCurrency": transaction_currency.upper(),
                "baseCurrency": base_currency.upper(),
            },
            separators=(",", ":"),
        )
        # Keep Decimal as an unquoted JSON number; converting through float can
        # round monetary values before the API receives them.
        request_body = f'{payload[:-1]},"amount":{amount}}}'
        response = self.session.post(
            f"{self.base_url}{self.PATH}",
            data=request_body,
            headers={"Content-Type": "application/json"},
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return self.parse_conversion(response.json())

    @staticmethod
    def parse_conversion(body: dict[str, Any]) -> QuotationRateConversion:
        assert body.get("code") == 200, f"当日汇率接口业务失败: code={body.get('code')} msg={body.get('msg')}"
        data = body.get("data")
        assert isinstance(data, dict), "当日汇率接口缺少 data 对象"
        required = {"baseCurrency", "transactionCurrency", "amount", "transactionAmount", "exchangeRate"}
        missing = required.difference(data)
        assert not missing, f"当日汇率接口缺少字段: {sorted(missing)}"
        return QuotationRateConversion(
            base_currency=str(data["baseCurrency"]).upper(),
            transaction_currency=str(data["transactionCurrency"]).upper(),
            amount=Decimal(str(data["amount"])),
            transaction_amount=Decimal(str(data["transactionAmount"])),
            exchange_rate=Decimal(str(data["exchangeRate"])),
        )

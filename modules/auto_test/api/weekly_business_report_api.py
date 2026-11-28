"""Read-only API access for the weekly business report regression suite."""

from __future__ import annotations

from typing import Any

import requests


class WeeklyBusinessReportAPI:
    """Small read-only client for report snapshots and their receivable bills.

    This client intentionally exposes no update or save operation. CI runs
    against shared TEST data, so write flows require an isolated report fixture
    before they can safely be exercised end to end.
    """

    REPORT_LIST_PATH = "/oms-report/weekly/report/list"
    REPORT_DETAIL_PATH = "/oms-report/weekly/report/{}"
    CUSTOMER_BILLS_PATH = "/oms-admin/sales/customerReceivableBill/listOrder"

    def __init__(self, session: requests.Session, api_base_url: str, *, timeout: tuple[int, int] = (10, 90)) -> None:
        self.session = session
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self.session.request(
            method,
            f"{self.api_base_url}{path}",
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("code") != 200:
            # Keep response bodies out of assertion output; they may contain
            # customer information from the shared test environment.
            raise AssertionError(f"Weekly report API returned an unsuccessful envelope: {method} {path}")
        return payload

    def list_reports(self, *, page_num: int = 1, page_size: int = 500) -> list[dict[str, Any]]:
        if page_num < 1 or not 1 <= page_size <= 1000:
            raise ValueError("Invalid weekly report page bounds")
        payload = self._request_json(
            "GET",
            self.REPORT_LIST_PATH,
            params={"pageNum": page_num, "pageSize": page_size},
        )
        data = payload.get("data") or {}
        rows = data.get("rows") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise AssertionError("Weekly report list response is missing data.rows")
        return rows

    def get_report(self, report_id: int | str) -> dict[str, Any]:
        if not str(report_id).isdigit() or int(report_id) <= 0:
            raise ValueError("report_id must be a positive integer")
        payload = self._request_json("GET", self.REPORT_DETAIL_PATH.format(report_id))
        report = payload.get("data")
        if not isinstance(report, dict):
            raise AssertionError("Weekly report detail response is missing data")
        return report

    def list_customer_bills(
        self,
        *,
        customer_id: int | str | None,
        customer_no: str,
        end_receivable_date: str,
        page_size: int = 2000,
    ) -> list[dict[str, Any]]:
        """Fetch all source-bill pages for one customer, bounded against runaway pagination."""
        if not customer_no or not end_receivable_date:
            raise ValueError("customer_no and end_receivable_date are required")
        if not 1 <= page_size <= 2000:
            raise ValueError("page_size must be between 1 and 2000")

        rows: list[dict[str, Any]] = []
        for page_num in range(1, 21):
            body = {
                "pageNum": page_num,
                "pageSize": page_size,
                "customerId": customer_id,
                "customerNo": customer_no,
                "beginReceivableDate": "",
                "endReceivableDate": end_receivable_date,
                "begincreateDate": "",
                "endcreateDate": "",
            }
            payload = self._request_json("POST", self.CUSTOMER_BILLS_PATH, json=body)
            page_rows = payload.get("rows")
            if page_rows is None:
                data = payload.get("data") or {}
                page_rows = data.get("rows") if isinstance(data, dict) else None
            if not isinstance(page_rows, list):
                raise AssertionError("Customer bill response is missing rows")
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                return rows
        raise AssertionError("Customer bill pagination exceeded 20 pages")

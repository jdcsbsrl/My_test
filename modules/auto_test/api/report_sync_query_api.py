"""API client for the sales order report sync query regression tests."""

from __future__ import annotations

from typing import Any

import requests


class ReportSyncQueryAPI:
    REPORT_PATH = "/oms-admin/sales/order/reportSyncQuery"
    ORDER_LIST_PATH = "/oms-admin/sales/order/batchListNew"
    ORDER_ITEM_PATH = "/oms-admin/sales/orderItem/queryAllList"

    def __init__(self, session: requests.Session, base_url: str) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.last_page_count = 0

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def query(self, payload: dict[str, Any]) -> requests.Response:
        return self.session.post(self._url(self.REPORT_PATH), json=payload, timeout=30)

    @staticmethod
    def validate_response_envelope(body: dict[str, Any]) -> None:
        assert isinstance(body, dict), "response should be a JSON object"
        assert "data" in body, "response should contain data"
        envelope = body["data"] if isinstance(body["data"], dict) else body
        assert isinstance(envelope.get("data"), list), "response data should be a list"
        assert isinstance(envelope.get("hasMore"), bool), "hasMore should be boolean"
        if envelope["hasMore"]:
            assert envelope.get("nextCursor") not in (None, ""), "nextCursor is required when hasMore=true"

    def query_all(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        orders: list[dict[str, Any]] = []
        cursor: Any | None = None
        for page_number in range(1, 1001):
            request_payload = dict(payload)
            if cursor not in (None, ""):
                request_payload["cursor"] = cursor
            response = self.query(request_payload)
            response.raise_for_status()
            body = response.json()
            self.validate_response_envelope(body)
            if body.get("code") not in (None, 0, "0", 200, "200"):
                raise AssertionError(f"reportSyncQuery failed: {body}")
            envelope = body.get("data") if isinstance(body.get("data"), dict) else body
            page = envelope.get("data")
            if not isinstance(page, list):
                raise AssertionError(f"reportSyncQuery data should be a list: {body}")
            orders.extend(item for item in page if isinstance(item, dict))
            if not envelope.get("hasMore"):
                self.last_page_count = page_number
                return orders
            next_cursor = envelope.get("nextCursor")
            if next_cursor in (None, "") or next_cursor == cursor:
                raise AssertionError(f"Invalid cursor response: {body}")
            cursor = next_cursor
        raise AssertionError("reportSyncQuery exceeded 1000 pages")

    def order_list(self, payload: dict[str, Any]) -> requests.Response:
        return self.session.post(self._url(self.ORDER_LIST_PATH), json=payload, timeout=30)

    def order_items(self, order_nos: list[str]) -> requests.Response:
        return self.session.post(
            self._url(self.ORDER_ITEM_PATH), json={"orderNoList": order_nos}, timeout=30
        )

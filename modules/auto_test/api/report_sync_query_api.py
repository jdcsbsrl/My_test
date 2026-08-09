"""Sales order report sync query API used by regression tests."""

from __future__ import annotations

from typing import Any

import requests


class ReportSyncQueryAPI:
    REPORT = "/oms-admin/sales/order/reportSyncQuery"
    ORDER_LIST = "/oms-admin/sales/order/batchListNew"
    ORDER_ITEMS = "/oms-admin/sales/orderItem/queryAllList"

    def __init__(self, session: requests.Session, api_base_url: str) -> None:
        self.session = session
        self.base_url = api_base_url.rstrip("/")
        for suffix in ("/oms-api", "/oms-uat-api"):
            if self.base_url.endswith(suffix + suffix):
                self.base_url = self.base_url[: -len(suffix)]

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(f"{self.base_url}{path}", json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        assert isinstance(body, dict), "response must be a JSON object"
        return body

    @staticmethod
    def envelope(body: dict[str, Any]) -> dict[str, Any]:
        data = body.get("data")
        return data if isinstance(data, dict) else body

    def query_page(self, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        body = self.post(self.REPORT, payload)
        code = body.get("code")
        if code not in (None, 0, "0", 200, "200"):
            raise AssertionError(f"reportSyncQuery business error: {body}")
        envelope = self.envelope(body)
        data = envelope.get("data")
        assert isinstance(data, list), f"response data must be a list: {body}"
        assert isinstance(envelope.get("hasMore"), bool), f"hasMore must be boolean: {body}"
        if envelope["hasMore"]:
            assert envelope.get("nextCursor") not in (None, ""), f"nextCursor is required: {body}"
        return [row for row in data if isinstance(row, dict)], envelope

    def query_all(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor: Any | None = None
        for _ in range(1000):
            request = dict(payload)
            if cursor not in (None, ""):
                request["cursor"] = cursor
            page, envelope = self.query_page(request)
            result.extend(page)
            if not envelope["hasMore"]:
                return result
            next_cursor = envelope["nextCursor"]
            assert next_cursor != cursor, "nextCursor must change"
            cursor = next_cursor
        raise AssertionError("cursor pagination exceeded 1000 pages")

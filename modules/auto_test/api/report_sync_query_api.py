"""Sales order report sync query API used by regression tests."""

from __future__ import annotations

from typing import Any

import requests


class CursorPaginationError(AssertionError):
    """Base error for a report cursor that cannot be consumed safely."""


class CursorPaginationLimitExceeded(CursorPaginationError):
    """Raised when a time window contains more pages than its budget."""


class CursorPaginationStalled(CursorPaginationError):
    """Raised when cursor pagination repeats or returns no forward progress."""


class ReportSyncQueryBusinessError(AssertionError):
    """Raised when reportSyncQuery returns a business-level error response."""


class ReportSyncQueryAPI:
    MAX_PAGES = 100
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
            raise ReportSyncQueryBusinessError(f"reportSyncQuery business error: {body}")
        envelope = self.envelope(body)
        data = envelope.get("data")
        assert isinstance(data, list), f"response data must be a list: {body}"
        assert isinstance(envelope.get("hasMore"), bool), f"hasMore must be boolean: {body}"
        if envelope["hasMore"]:
            assert envelope.get("nextCursor") not in (None, ""), f"nextCursor is required: {body}"
        return [row for row in data if isinstance(row, dict)], envelope

    def query_all(self, payload: dict[str, Any], max_pages: int | None = None) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor: Any | None = None
        page_budget = max_pages or self.MAX_PAGES
        seen_cursors: set[str] = set()
        seen_pages: set[tuple[str, ...]] = set()
        for page_number in range(1, page_budget + 1):
            request = dict(payload)
            if cursor not in (None, ""):
                request["cursor"] = cursor
            page, envelope = self.query_page(request)
            page_fingerprint = tuple(
                str(row.get("id") or row.get("orderNo") or repr(sorted(row.items()))) for row in page
            )
            if page_fingerprint and page_fingerprint in seen_pages:
                raise CursorPaginationStalled(
                    f"report cursor returned duplicate page: pages={page_number}, orders={len(result)}"
                )
            seen_pages.add(page_fingerprint)
            result.extend(page)
            if not envelope["hasMore"]:
                return result
            next_cursor = envelope["nextCursor"]
            cursor_key = str(next_cursor)
            if next_cursor == cursor or cursor_key in seen_cursors:
                raise CursorPaginationStalled(
                    f"report cursor made no forward progress: pages={page_number}, orders={len(result)}"
                )
            seen_cursors.add(cursor_key)
            cursor = next_cursor
        raise CursorPaginationLimitExceeded(
            f"report cursor pagination exceeded budget: pages={page_budget}, orders={len(result)}"
        )

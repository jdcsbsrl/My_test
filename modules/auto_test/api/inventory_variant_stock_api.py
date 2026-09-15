"""API client for the online product stock query endpoint."""

from __future__ import annotations

from typing import Any

import requests


class InventoryVariantStockAPI:
    """Small read-only client for online product stock queries."""

    PATH = "/oms-admin/base/inventory/variant/querySkuStockPage"
    REQUEST_TIMEOUT = (10, 60)

    def __init__(self, session: requests.Session, api_base_url: str) -> None:
        self.session = session
        self.base_url = api_base_url.rstrip("/")

    def query_page(self, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Query one page and return the decoded response envelope."""
        response = self.session.get(
            f"{self.base_url}{self.PATH}",
            params=params or {},
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        assert isinstance(body, dict), "库存查询接口响应必须是 JSON 对象"
        return body

    @staticmethod
    def envelope(body: dict[str, Any]) -> dict[str, Any]:
        """Return the response envelope for direct or wrapped API responses."""
        data = body.get("data")
        if isinstance(data, dict):
            return data
        return body

    @classmethod
    def rows(cls, body: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract rows while enforcing the documented response shape."""
        envelope = cls.envelope(body)
        rows = envelope.get("rows")
        assert isinstance(rows, list), f"响应 rows 必须是数组，实际响应: {body}"
        assert all(isinstance(row, dict) for row in rows), "响应 rows 中的元素必须是对象"
        return rows

    @classmethod
    def assert_success(cls, body: dict[str, Any]) -> dict[str, Any]:
        """Validate the common success envelope and return it."""
        envelope = cls.envelope(body)
        code = envelope.get("code")
        assert code in (None, 0, "0", 200, "200"), f"接口业务失败: {body}"
        assert isinstance(envelope.get("total"), int), f"响应 total 必须是整数: {body}"
        assert isinstance(envelope.get("msg"), str), f"响应 msg 必须是字符串: {body}"
        cls.rows(body)
        return envelope

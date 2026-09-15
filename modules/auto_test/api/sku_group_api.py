"""Client for combination SKU detail queries."""

from __future__ import annotations

from typing import Any

import requests


class SKUGroupAPI:
    """Read-only client for combination SKU definitions."""

    PATH = "/oms-admin/base/skuGroup/list"
    REQUEST_TIMEOUT = (10, 60)

    def __init__(self, session: requests.Session, api_base_url: str) -> None:
        self.session = session
        self.base_url = api_base_url.rstrip("/")

    def list_page(self, group_sku_id: str, page_num: int = 1, page_size: int = 20) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}{self.PATH}",
            params={"pageSize": page_size, "pageNum": page_num, "groupSkuId": group_sku_id},
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        assert isinstance(body, dict), "组合 SKU 接口响应必须是 JSON 对象"
        return body

    @classmethod
    def rows(cls, body: dict[str, Any]) -> list[dict[str, Any]]:
        rows = body.get("rows")
        assert isinstance(rows, list), f"组合 SKU 响应 rows 必须是数组: {body}"
        assert all(isinstance(row, dict) for row in rows), "组合 SKU rows 元素必须是对象"
        return rows

    @classmethod
    def assert_success(cls, body: dict[str, Any]) -> dict[str, Any]:
        assert body.get("code") in (None, 0, "0", 200, "200"), f"组合 SKU 接口业务失败: {body}"
        assert isinstance(body.get("total"), int), f"组合 SKU total 必须是整数: {body}"
        cls.rows(body)
        return body

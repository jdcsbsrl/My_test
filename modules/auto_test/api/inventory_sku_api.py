"""Client for ERP inventory SKU list queries used by stock-state checks."""

from __future__ import annotations

from typing import Any

import requests


class InventorySKUAPI:
    """Read-only client for the ERP inventory SKU endpoint."""

    PATH = "/oms-admin/base/inventory/listNew"
    REQUEST_TIMEOUT = (10, 60)

    def __init__(self, session: requests.Session, api_base_url: str) -> None:
        self.session = session
        self.base_url = api_base_url.rstrip("/")

    def list_page(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}{self.PATH}",
            json=payload,
            timeout=self.REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
        assert isinstance(body, dict), "库存 SKU 接口响应必须是 JSON 对象"
        return body

    @staticmethod
    def table(body: dict[str, Any]) -> dict[str, Any]:
        data = body.get("data")
        assert isinstance(data, dict), f"库存 SKU 响应缺少 data: {body}"
        table = data.get("tableDataInfo")
        assert isinstance(table, dict), f"库存 SKU 响应缺少 data.tableDataInfo: {body}"
        return table

    @classmethod
    def rows(cls, body: dict[str, Any]) -> list[dict[str, Any]]:
        rows = cls.table(body).get("rows")
        if rows is None:
            return []
        assert isinstance(rows, list), f"库存 SKU 响应 rows 必须是数组: {body}"
        assert all(isinstance(row, dict) for row in rows), "库存 SKU rows 元素必须是对象"
        return rows

    @classmethod
    def assert_success(cls, body: dict[str, Any]) -> dict[str, Any]:
        code = body.get("code")
        assert code in (None, 0, "0", 200, "200"), f"库存 SKU 接口业务失败: {body}"
        table = cls.table(body)
        assert table.get("code") in (None, 0, "0", 200, "200"), f"库存 SKU 分页业务失败: {body}"
        assert isinstance(table.get("total"), int), f"库存 SKU total 必须是整数: {body}"
        assert table.get("rows") is None or isinstance(
            table.get("rows"), list
        ), f"库存 SKU rows 必须是数组或空值: {body}"
        return table

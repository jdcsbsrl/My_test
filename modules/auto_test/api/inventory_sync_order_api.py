"""Read-only sales-order source API for inventory-sync regression checks."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import requests

from modules.auto_test.core.inventory_sync_calculator import OrderLine


class InventorySyncOrderAPI:
    ORDER_LIST = "/oms-admin/sales/order/batchListNew"
    ORDER_DETAILS = "/oms-admin/sales/orderItem/queryAllList"
    REQUEST_TIMEOUT = (10, 90)

    def __init__(self, session: requests.Session, api_base_url: str) -> None:
        self.session = session
        self.base_url = api_base_url.rstrip("/")

    def fetch_order_lines(self, order_numbers: list[str]) -> list[OrderLine]:
        normalized_numbers = list(dict.fromkeys(number.strip() for number in order_numbers if number.strip()))
        if not normalized_numbers:
            raise ValueError("inventory sync regression requires explicit seed order numbers")

        orders = self._post(
            self.ORDER_LIST,
            {
                "pageNum": 1,
                "pageSize": max(100, len(normalized_numbers)),
                "orderByColumn": "",
                "isAsc": "",
                "orderNoList": normalized_numbers,
                "storeIds": "",
                "orderStatus": "",
            },
        )
        table = (orders.get("data") or {}).get("tableDataInfo") or {}
        order_rows = table.get("rows") or []
        indexed_orders = {str(row.get("orderNo")): row for row in order_rows if row.get("orderNo")}
        missing = sorted(set(normalized_numbers) - set(indexed_orders))
        if missing:
            raise AssertionError(f"预置订单查询不完整，缺少 {len(missing)} 条订单")
        if int(table.get("total", len(order_rows))) != len(indexed_orders):
            raise AssertionError("预置订单查询存在分页或重复记录，不能用于完整对账")

        header_hold_flags = {
            order_number: _as_bool(indexed_orders[order_number].get("isHold"), field="order isHold")
            for order_number in normalized_numbers
        }

        details = self._post(self.ORDER_DETAILS, {"orderNoList": normalized_numbers}).get("data") or {}
        missing_details = sorted(set(normalized_numbers) - set(details))
        if missing_details:
            raise AssertionError(f"订单明细查询不完整，缺少 {len(missing_details)} 张订单")

        result: list[OrderLine] = []
        for order_number in normalized_numbers:
            header = indexed_orders[order_number]
            status = str(header.get("orderStatus", ""))
            lines = details[order_number]
            if not isinstance(lines, list):
                raise AssertionError(f"订单 {order_number} 明细必须为数组")
            for detail in lines:
                if not isinstance(detail, dict):
                    raise AssertionError(f"订单 {order_number} 明细项必须为对象")
                # Combination rows may also carry a child itemId; groupSkuId
                # identifies the ordered combination SKU.
                sku = str(detail.get("groupSkuId") or detail.get("itemId") or "").strip()
                if not sku:
                    continue
                quantity_value = detail.get("quantity")
                if detail.get("groupSkuId"):
                    quantity_value = detail.get("groupSkuQty", quantity_value)
                if quantity_value in (None, ""):
                    raise AssertionError(f"订单 {order_number} SKU {sku} 明细缺少数量")
                result.append(
                    OrderLine(
                        status=status,
                        is_hold=header_hold_flags[order_number]
                        or _as_bool(detail.get("isHold"), field="order item isHold"),
                        deficit_flag=_detail_deficit_flag(detail, status=status),
                        sku=sku,
                        quantity=Decimal(str(quantity_value)),
                        store_name=str(header.get("storeName") or "").strip(),
                    )
                )
        return result

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self.session.post(f"{self.base_url}{path}", json=payload, timeout=self.REQUEST_TIMEOUT)
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise AssertionError(f"订单接口响应必须为JSON对象: {path}")
        if body.get("code") not in (200, "200", 0, "0"):
            raise AssertionError(f"订单接口业务失败: {path}, code={body.get('code')}")
        return body


def _as_bool(value: Any, *, field: str) -> bool:
    if value in (None, False, 0, "0", "", "false", "False"):
        return False
    if value in (True, 1, "1", "true", "True"):
        return True
    raise AssertionError(f"{field} 值不在已知范围内")


def _as_flag(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if value in (0, "0"):
        return 0
    if value in (1, "1"):
        return 1
    raise AssertionError("deficitFlag 仅允许 0 或 1")


def _detail_deficit_flag(detail: dict[str, Any], *, status: str) -> int | None:
    """Resolve an unpaid combination wrapper from its child detail rows."""
    flag = _as_flag(detail.get("deficitFlag"))
    if status != "5" or flag is not None:
        return flag
    if not detail.get("groupSkuId"):
        raise AssertionError("待付款普通 SKU 明细缺少deficitFlag")

    children = detail.get("detail")
    if not isinstance(children, list) or not children:
        raise AssertionError("待付款组合 SKU 明细缺少子 SKU deficitFlag")
    child_flags: list[int] = []
    for child in children:
        if not isinstance(child, dict):
            raise AssertionError("待付款组合 SKU 子明细必须为对象")
        child_flag = _as_flag(child.get("deficitFlag"))
        if child_flag not in {0, 1}:
            raise AssertionError("待付款组合 SKU 子明细缺少deficitFlag")
        child_flags.append(child_flag)
    if len(set(child_flags)) != 1:
        raise AssertionError("同一待付款组合 SKU 的子明细 deficitFlag 不一致")
    return child_flags[0]

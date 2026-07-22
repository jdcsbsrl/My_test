"""Sales order API facade."""

from __future__ import annotations

from typing import Any

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import get_config
from modules.auto_test.reporting.allure_http import attach_request_info, step


class SalesOrderFacade:
    def __init__(self, client: APIClient) -> None:
        self._client = client
        self._config = get_config()
        self._base = str(self._config.get("api.sales_order_resource", "/oms-admin/sales/order"))

    @property
    def client(self) -> APIClient:
        return self._client

    def batch_list_new(self, payload: dict[str, Any]) -> requests.Response:
        endpoint = f"{self._base}/batchListNew"
        with step(f"查询销售订单列表(batchListNew) {endpoint}"):
            response = self._client.post(endpoint, json=payload)
            attach_request_info(response)
        return response

    def query_orders(
        self,
        page_num: int = 1,
        page_size: int = 100,
        **filters: Any,
    ) -> requests.Response:
        payload: dict[str, Any] = {
            "pageNum": page_num,
            "pageSize": page_size,
            "orderByColumn": "",
            "isAsc": "",
            **filters,
        }
        return self.batch_list_new(payload)

    def export_orders(self, payload: dict[str, Any]) -> requests.Response:
        endpoint = f"{self._base}/batch/orderExport"
        with step(f"导出销售订单 {endpoint}"):
            response = self._client.post(endpoint, json=payload)
            attach_request_info(response)
        return response

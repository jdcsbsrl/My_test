from typing import Any
from urllib.parse import urlsplit

import allure

from modules.auto_test.api.base_api import BaseAPI
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.secret_provider import get_secret


class OpenAPIClient(BaseAPI):
    """OpenAPI客户端，用于调用物流、账单、订单、库存、报价等API"""

    def __init__(self, app_key: str, app_secret: str, client: APIClient | None = None) -> None:
        super().__init__(client)
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = get_secret("OPENAPI_BASE_URL")

    def _get_auth_headers(self) -> dict[str, str]:
        """获取认证头"""
        return {"Content-Type": "application/json", "X-App-Key": self.app_key, "X-App-Secret": self.app_secret}

    def _endpoint(self, path: str) -> str:
        """Build an endpoint without allowing credentials to enter its query string."""
        base_url = str(self.base_url or "").strip()
        parsed = urlsplit(base_url)
        if (
            not base_url
            or parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OPENAPI_BASE_URL must be an HTTP(S) origin without credentials or query parameters")
        return f"{base_url.rstrip('/')}{path}"

    @allure.step("物流查询API")
    def query_logistics_page(self, params: dict[str, Any] | None = None) -> Any:
        """
        物流查询API

        Endpoint: POST /oms-admin/system/customerApiResource/openapi/logistics/queryLogisticsPage
        """
        endpoint = self._endpoint("/oms-admin/system/customerApiResource/openapi/logistics/queryLogisticsPage")
        headers = self._get_auth_headers()
        response = self.post(endpoint, json=params or {}, headers=headers)
        self.attach_request_info(response)
        return response

    @allure.step("账单查询API")
    def query_bill_page(self, params: dict[str, Any] | None = None) -> Any:
        """
        账单查询API

        Endpoint: POST /oms-admin/system/customerApiResource/openapi/order/queryBillPage
        """
        endpoint = self._endpoint("/oms-admin/system/customerApiResource/openapi/order/queryBillPage")
        headers = self._get_auth_headers()
        response = self.post(endpoint, json=params or {}, headers=headers)
        self.attach_request_info(response)
        return response

    @allure.step("账单明细查询API")
    def query_bill_item(self, params: dict[str, Any] | None = None) -> Any:
        """
        账单明细查询API

        Endpoint: POST /oms-admin/system/customerApiResource/openapi/order/queryBillItem
        """
        endpoint = self._endpoint("/oms-admin/system/customerApiResource/openapi/order/queryBillItem")
        headers = self._get_auth_headers()
        response = self.post(endpoint, json=params or {}, headers=headers)
        self.attach_request_info(response)
        return response

    @allure.step("报价查询API")
    def query_quotation_page(self, params: dict[str, Any] | None = None) -> Any:
        """
        报价查询API

        Endpoint: POST /oms-admin/system/customerApiResource/openapi/order/queryQuotationPage
        """
        endpoint = self._endpoint("/oms-admin/system/customerApiResource/openapi/order/queryQuotationPage")
        headers = self._get_auth_headers()
        response = self.post(endpoint, json=params or {}, headers=headers)
        self.attach_request_info(response)
        return response

    @allure.step("订单查询API")
    def query_order_page(self, params: dict[str, Any] | None = None) -> Any:
        """
        订单查询API

        Endpoint: POST /oms-admin/system/customerApiResource/openapi/order/queryOrderPage
        """
        endpoint = self._endpoint("/oms-admin/system/customerApiResource/openapi/order/queryOrderPage")
        headers = self._get_auth_headers()
        response = self.post(endpoint, json=params or {}, headers=headers)
        self.attach_request_info(response)
        return response

    @allure.step("SKU库存查询API")
    def query_sku_stock_page(self, params: dict[str, Any] | None = None) -> Any:
        """
        SKU库存查询API

        Endpoint: POST /oms-admin/system/customerApiResource/openapi/order/querySkuStockPage
        """
        endpoint = self._endpoint("/oms-admin/system/customerApiResource/openapi/order/querySkuStockPage")
        headers = self._get_auth_headers()
        response = self.post(endpoint, json=params or {}, headers=headers)
        self.attach_request_info(response)
        return response

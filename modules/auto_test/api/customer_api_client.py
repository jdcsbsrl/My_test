from typing import Any

import allure

from modules.auto_test.api.base_api import BaseAPI
from modules.auto_test.core.api_client import APIClient


class CustomerApiClientAPI(BaseAPI):
    def __init__(self, client: APIClient | None = None) -> None:
        super().__init__(client)
        self.base_path = "/system/customerApiClient"

    @allure.step("查询外部客户AppKey和秘钥列表")
    def list(
        self,
        page_num: int = 1,
        page_size: int = 10,
        customer_name: str | None = None,
        customer_id: str | None = None,
        app_name: str | None = None,
        app_key: str | None = None,
        status: int | None = None,
        order_by_column: str = "",
        is_asc: str = "",
        **filters: Any,
    ) -> Any:
        params = {
            "pageNum": page_num,
            "pageSize": page_size,
            "orderByColumn": order_by_column,
            "isAsc": is_asc,
        }
        if customer_name:
            params["customerName"] = customer_name
        if customer_id:
            params["customerId"] = customer_id
        if app_name:
            params["appName"] = app_name
        if app_key:
            params["appKey"] = app_key
        if status is not None:
            params["status"] = status
        params.update(filters)

        endpoint = f"{self.base_path}/list"
        response = self.get(endpoint, params=params)
        self.attach_request_info(response)
        return response

    @allure.step("获取外部客户AppKey和秘钥详细信息")
    def get_by_id(self, id: int) -> Any:
        endpoint = f"{self.base_path}/{id}"
        response = self.get(endpoint)
        self.attach_request_info(response)
        return response

    @allure.step("新增外部客户AppKey和秘钥")
    def add(self, payload: dict[str, Any]) -> Any:
        endpoint = f"{self.base_path}"
        response = self.post(endpoint, json=payload)
        self.attach_request_info(response)
        return response

    @allure.step("修改外部客户AppKey和秘钥")
    def edit(self, payload: dict[str, Any]) -> Any:
        endpoint = f"{self.base_path}/edit"
        response = self.put(endpoint, json=payload)
        self.attach_request_info(response)
        return response

    @allure.step("删除外部客户AppKey和秘钥")
    def delete(self, ids: list[int]) -> Any:
        endpoint = f"{self.base_path}/{ids}"
        response = self.delete(endpoint)
        self.attach_request_info(response)
        return response

    @allure.step("全部停用")
    def stop_app_secret(self, ids: list[int]) -> Any:
        endpoint = f"{self.base_path}/edit/stopAppSecret"
        response = self.put(endpoint, json={"ids": ids})
        self.attach_request_info(response)
        return response

    @allure.step("生成秘钥")
    def generate_secret(self) -> Any:
        endpoint = f"{self.base_path}/get"
        response = self.get(endpoint)
        self.attach_request_info(response)
        return response

    @allure.step("重置秘钥")
    def reset_secret(self) -> Any:
        endpoint = f"{self.base_path}/updateSecret"
        response = self.get(endpoint)
        self.attach_request_info(response)
        return response

    @allure.step("导出外部客户AppKey和秘钥列表")
    def export(self, **filters: Any) -> Any:
        endpoint = f"{self.base_path}/export"
        response = self.post(endpoint, params=filters)
        self.attach_request_info(response)
        return response

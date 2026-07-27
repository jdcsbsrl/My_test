from __future__ import annotations

from typing import Any

import allure

from modules.auto_test.api.base_api import BaseAPI
from modules.auto_test.core.api_client import APIClient


class CustomerApiResourceAPI(BaseAPI):
    def __init__(self, client: APIClient | None = None) -> None:
        super().__init__(client)
        self.base_path = "/system/customerApiResource"

    @allure.step("查询对外接口列表")
    def list(
        self,
        page_num: int = 1,
        page_size: int = 10,
        api_code: str | None = None,
        api_name: str | None = None,
        path: str | None = None,
        method: str | None = None,
        description: str | None = None,
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
        if api_code:
            params["apiCode"] = api_code
        if api_name:
            params["apiName"] = api_name
        if path:
            params["path"] = path
        if method:
            params["method"] = method
        if description:
            params["description"] = description
        params.update(filters)

        endpoint = f"{self.base_path}/list"
        response = self.post(endpoint, params=params)
        self.attach_request_info(response)
        return response

    @allure.step("获取对外接口详细信息")
    def get_by_id(self, id: int) -> Any:
        endpoint = f"{self.base_path}/{id}"
        response = self.get(endpoint)
        self.attach_request_info(response)
        return response

    @allure.step("新增对外接口")
    def add(self, payload: dict[str, Any]) -> Any:
        endpoint = f"{self.base_path}"
        response = self.post(endpoint, json=payload)
        self.attach_request_info(response)
        return response

    @allure.step("修改对外接口")
    def edit(self, payload: dict[str, Any]) -> Any:
        endpoint = f"{self.base_path}"
        response = self.put(endpoint, json=payload)
        self.attach_request_info(response)
        return response

    @allure.step("删除对外接口")
    def delete(self, ids: list[int]) -> Any:
        endpoint = f"{self.base_path}/{ids}"
        response = super().delete(endpoint)
        self.attach_request_info(response)
        return response

    @allure.step("导出对外接口列表")
    def export(self, **filters: Any) -> Any:
        endpoint = f"{self.base_path}/export"
        response = self.post(endpoint, params=filters)
        self.attach_request_info(response)
        return response

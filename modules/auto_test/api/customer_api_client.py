from __future__ import annotations

import re
from typing import Any

import allure

from modules.auto_test.api.base_api import BaseAPI
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.drivers.http_driver import HttpDriver


class CustomerApiClientAPI(BaseAPI):
    def __init__(self, client: APIClient | None = None) -> None:
        super().__init__(client)
        self.base_path = "/system/customerApiClient"

    @staticmethod
    def _validate_id(value: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("Customer identifiers must be positive integers")
        return value

    @classmethod
    def _validate_ids(cls, values: list[int]) -> list[int]:
        if not isinstance(values, list) or not values:
            raise ValueError("At least one customer identifier is required")
        return [cls._validate_id(value) for value in values]

    @staticmethod
    def _split_sensitive_filters(filters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        query_params: dict[str, Any] = {}
        body_params: dict[str, Any] = {}
        for key, value in filters.items():
            if HttpDriver._is_sensitive_key(key):
                body_params[key] = value
            else:
                query_params[key] = value
        return query_params, body_params

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
        if isinstance(page_num, bool) or not isinstance(page_num, int) or page_num < 1:
            raise ValueError("page_num must be a positive integer")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        if order_by_column and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", order_by_column):
            raise ValueError("order_by_column contains unsafe characters")
        if is_asc and is_asc.lower() not in {"asc", "desc"}:
            raise ValueError("is_asc must be asc or desc")
        for key in filters:
            if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(key)):
                raise ValueError("Filter names must contain only letters, digits, and underscores")
        filters_to_send = {
            "pageNum": page_num,
            "pageSize": page_size,
            "orderByColumn": order_by_column,
            "isAsc": is_asc,
        }
        if customer_name:
            filters_to_send["customerName"] = customer_name
        if customer_id:
            filters_to_send["customerId"] = customer_id
        if app_name:
            filters_to_send["appName"] = app_name
        if app_key:
            filters_to_send["appKey"] = app_key
        if status is not None:
            filters_to_send["status"] = status
        filters_to_send.update(filters)

        endpoint = f"{self.base_path}/list"
        query_params, body_params = self._split_sensitive_filters(filters_to_send)
        request_kwargs: dict[str, Any] = {"params": query_params}
        if body_params:
            request_kwargs["json"] = body_params
        response = self.get(endpoint, **request_kwargs)
        return response

    @allure.step("获取外部客户AppKey和秘钥详细信息")
    def get_by_id(self, id: int) -> Any:
        id = self._validate_id(id)
        endpoint = f"{self.base_path}/{id}"
        response = self.get(endpoint)
        return response

    @allure.step("新增外部客户AppKey和秘钥")
    def add(self, payload: dict[str, Any]) -> Any:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        endpoint = f"{self.base_path}"
        response = self.post(endpoint, json=payload)
        return response

    @allure.step("修改外部客户AppKey和秘钥")
    def edit(self, payload: dict[str, Any]) -> Any:
        if not isinstance(payload, dict):
            raise TypeError("payload must be a dictionary")
        endpoint = f"{self.base_path}/edit"
        response = self.put(endpoint, json=payload)
        return response

    @allure.step("删除外部客户AppKey和秘钥")
    def delete(self, ids: list[int]) -> Any:
        ids = self._validate_ids(ids)
        endpoint = f"{self.base_path}/{ids}"
        response = super().delete(endpoint)
        return response

    @allure.step("全部停用")
    def stop_app_secret(self, ids: list[int]) -> Any:
        ids = self._validate_ids(ids)
        endpoint = f"{self.base_path}/edit/stopAppSecret"
        response = self.put(endpoint, json={"ids": ids})
        return response

    @allure.step("生成秘钥")
    def generate_secret(self) -> Any:
        endpoint = f"{self.base_path}/get"
        response = self.get(endpoint)
        return response

    @allure.step("重置秘钥")
    def reset_secret(self) -> Any:
        endpoint = f"{self.base_path}/updateSecret"
        response = self.get(endpoint)
        return response

    @allure.step("导出外部客户AppKey和秘钥列表")
    def export(self, **filters: Any) -> Any:
        endpoint = f"{self.base_path}/export"
        query_params, body_params = self._split_sensitive_filters(filters)
        request_kwargs: dict[str, Any] = {"params": query_params}
        if body_params:
            request_kwargs["json"] = body_params
        response = self.post(endpoint, **request_kwargs)
        return response

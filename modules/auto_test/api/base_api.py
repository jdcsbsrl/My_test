from typing import Any

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.reporting.allure_http import attach_request_info, step


class BaseAPI:
    """Thin HTTP + Allure reporting; prefer facades for new code."""

    def __init__(self, client: APIClient | None = None) -> None:
        self.client = client or APIClient()

    def get(self, endpoint: str, **kwargs: Any) -> requests.Response:
        with step(f"API GET {endpoint}"):
            return self.client.get(endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> requests.Response:
        with step(f"API POST {endpoint}"):
            return self.client.post(endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs: Any) -> requests.Response:
        with step(f"API PUT {endpoint}"):
            return self.client.put(endpoint, **kwargs)

    def patch(self, endpoint: str, **kwargs: Any) -> requests.Response:
        with step(f"API PATCH {endpoint}"):
            return self.client.patch(endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> requests.Response:
        with step(f"API DELETE {endpoint}"):
            return self.client.delete(endpoint, **kwargs)

    def attach_request_info(self, response: requests.Response) -> None:
        attach_request_info(response)

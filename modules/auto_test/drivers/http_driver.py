"""HTTP transport only: session, retries, timeouts, optional proxy. No Allure / pytest."""

from __future__ import annotations

import json
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from modules.auto_test.core.config_manager import ConfigManager, get_config
from modules.auto_test.core.logger import get_logger
from modules.auto_test.core.secret_manager import get_secret_manager

logger = get_logger()


class HttpDriver:
    def __init__(self, base_url: str, config: ConfigManager | None = None) -> None:
        self._config = config or get_config()
        self.base_url = base_url.rstrip("/")
        self.timeout = int(self._config.get("api.timeout", 30))
        self.session = requests.Session()

        retries = Retry(
            total=int(self._config.get("api.retries", 3)),
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.session.verify = self._config.get("api.verify_ssl", True)

        secret_manager = get_secret_manager()
        if secret_manager:
            proxy = secret_manager.get_proxy()
            if proxy:
                self.session.proxies.update({"http": proxy, "https": proxy})

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _log_request(self, method: str, url: str, **kwargs: Any) -> None:
        logger.debug(f"Request: {method} {url}")
        if "json" in kwargs:
            logger.debug(f"Request body: {json.dumps(kwargs['json'], ensure_ascii=False)}")
        if "params" in kwargs:
            logger.debug(f"Request params: {kwargs['params']}")
        if "headers" in kwargs:
            logger.debug(f"Request headers: {kwargs['headers']}")

    def _log_response(self, response: requests.Response) -> None:
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response time: {response.elapsed.total_seconds():.3f}s")
        try:
            body = response.json()
            logger.debug(f"Response body: {json.dumps(body, ensure_ascii=False, indent=2)}")
        except (json.JSONDecodeError, ValueError):
            logger.debug(f"Response text: {response.text[:500]}")

    def request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        url = self._build_url(endpoint)
        kwargs.setdefault("timeout", self.timeout)

        self._log_request(method, url, **kwargs)
        response = self.session.request(method, url, **kwargs)
        self._log_response(response)
        return response

    def get(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.request("PUT", endpoint, **kwargs)

    def patch(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.request("PATCH", endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> requests.Response:
        return self.request("DELETE", endpoint, **kwargs)

    def close(self) -> None:
        self.session.close()

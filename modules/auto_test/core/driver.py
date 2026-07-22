"""Simple HTTP driver for API requests."""

from typing import Any

import requests
from requests import RequestException

from auto_test.core.logger import get_logger

logger = get_logger()


class HttpDriver:
    def __init__(self, base_url: str, config: Any = None) -> None:
        self._base_url = base_url or ""
        self._session = requests.Session()
        self.timeout = 30
        self._verify_ssl = True
        if config:
            self._verify_ssl = config.get("api.verify_ssl", True)
            self.timeout = config.get("api.timeout", 30)

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def session(self) -> requests.Session:
        return self._session

    def _build_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        if endpoint.startswith("/") and self._base_url:
            return f"{self._base_url}{endpoint}"
        return endpoint

    def _handle_response(self, response: requests.Response) -> dict[str, Any]:
        try:
            return response.json()
        except Exception:
            return {"text": response.text, "status_code": response.status_code}

    def request(self, method: str, endpoint: str, **kwargs: Any) -> requests.Response:
        url = self._build_url(endpoint)
        logger.info("%s %s", method.upper(), url)
        try:
            response = self._session.request(
                method=method.upper(), url=url, timeout=self.timeout, verify=self._verify_ssl, **kwargs
            )
            logger.info("Response: %s", response.status_code)
            return response
        except RequestException as e:
            logger.error("Request failed: %s", str(e))
            raise

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
        self._session.close()

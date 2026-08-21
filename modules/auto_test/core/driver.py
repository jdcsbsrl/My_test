"""Simple HTTP driver for API requests."""

import json
import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import requests
from requests import RequestException

from modules.auto_test.core.logger import get_logger
from modules.auto_test.drivers.http_driver import HttpDriver as SecureHttpDriver

logger = get_logger()


class HttpDriver:
    """Backward-compatible driver that delegates redaction to the current transport."""

    @staticmethod
    def _is_sensitive_key(key: Any) -> bool:
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        return SecureHttpDriver._is_sensitive_key(key) or normalized in {"apikey", "apiSecret".lower()}

    @staticmethod
    def _redact(value: Any) -> Any:
        return SecureHttpDriver._redact(value)

    @classmethod
    def _redact_text(cls, value: str) -> str:
        redacted = SecureHttpDriver._redact_text(value)
        return re.sub(r"(?i)(https?://[^\s?#]+)\?[^\s]+", r"\1?[REDACTED]", redacted)

    @classmethod
    def _redact_url(cls, url: str) -> str:
        return SecureHttpDriver._redact_url(url)

    @classmethod
    def _query_has_sensitive_key(cls, query: str) -> bool:
        return any(cls._is_sensitive_key(key) for key, _ in parse_qsl(query, keep_blank_values=True))

    @classmethod
    def _safe_exception_message(cls, error: BaseException) -> str:
        return cls._redact_text(str(error))

    @classmethod
    def _sanitize_exception(cls, error: RequestException) -> None:
        if error.args:
            error.args = tuple(cls._redact_text(item) if isinstance(item, str) else item for item in error.args)

    @classmethod
    def _protect_query_params(cls, kwargs: dict[str, Any]) -> None:
        params = kwargs.get("params")
        if params is None:
            return
        if isinstance(params, dict):
            safe_params: dict[str, Any] = {}
            sensitive_params: dict[str, Any] = {}
            for key, value in params.items():
                if cls._is_sensitive_key(key):
                    sensitive_params[key] = value
                else:
                    safe_params[key] = value
            if sensitive_params:
                kwargs["params"] = safe_params
                body = kwargs.get("json")
                if body is None:
                    kwargs["json"] = sensitive_params
                elif isinstance(body, dict):
                    kwargs["json"] = {**body, **sensitive_params}
                else:
                    raise ValueError("Sensitive query parameters require a JSON object body")
            return
        if isinstance(params, str):
            if cls._query_has_sensitive_key(params):
                raise ValueError("Sensitive query parameters are not allowed")
            return
        if isinstance(params, (list, tuple)):
            safe_params = []
            sensitive_params = {}
            for item in params:
                if not isinstance(item, (list, tuple)) or len(item) != 2:
                    safe_params.append(item)
                    continue
                key, value = item
                if cls._is_sensitive_key(key):
                    sensitive_params[key] = value
                else:
                    safe_params.append(item)
            if sensitive_params:
                kwargs["params"] = safe_params
                body = kwargs.get("json")
                if body is None:
                    kwargs["json"] = sensitive_params
                elif isinstance(body, dict):
                    kwargs["json"] = {**body, **sensitive_params}
                else:
                    raise ValueError("Sensitive query parameters require a JSON object body")

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
        value = str(endpoint or "")
        parsed = urlsplit(value)
        if parsed.query and self._query_has_sensitive_key(parsed.query):
            raise ValueError("Sensitive query parameters are not allowed")
        base_query = urlsplit(self._base_url).query
        if base_query and self._query_has_sensitive_key(base_query):
            raise ValueError("Sensitive query parameters are not allowed")
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
        self._protect_query_params(kwargs)
        url = self._build_url(endpoint)
        logger.info(f"{method.upper()} {self._redact_url(url)}")
        if "json" in kwargs:
            logger.debug(f"Request body: {json.dumps(self._redact(kwargs['json']), ensure_ascii=False)}")
        if "params" in kwargs:
            logger.debug(f"Request params: {self._redact(kwargs['params'])}")
        if "headers" in kwargs:
            logger.debug(f"Request headers: {self._redact(kwargs['headers'])}")
        try:
            response = self._session.request(
                method=method.upper(), url=url, timeout=self.timeout, verify=self._verify_ssl, **kwargs
            )
            logger.info("Response: %s", response.status_code)
            return response
        except RequestException as e:
            self._sanitize_exception(e)
            logger.error(f"Request failed: {self._safe_exception_message(e)}")
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

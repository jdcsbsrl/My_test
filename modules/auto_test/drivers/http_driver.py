"""HTTP transport only: session, retries, timeouts, optional proxy. No Allure / pytest."""

from __future__ import annotations

import json
import posixpath
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

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
        self.base_url = self._validate_base_url(base_url)
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

    def _validate_base_url(self, base_url: str) -> str:
        value = str(base_url or "").strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "\\" in parsed.path
            or ".." in parsed.path.split("/")
        ):
            raise ValueError(f"Invalid HTTP base URL: {base_url!r}")
        if hasattr(self._config, "validate_endpoint"):
            return self._config.validate_endpoint(value, purpose="HTTP base", allow_external=False).rstrip("/")
        return value

    def _build_url(self, endpoint: str) -> str:
        value = str(endpoint or "").strip()
        if value.startswith("//"):
            raise ValueError(f"Protocol-relative endpoints are not allowed: {endpoint!r}")
        if any(char in value for char in ("\r", "\n", "\\")) or ".." in value.split("?")[0].split("/"):
            raise ValueError(f"Unsafe endpoint path: {endpoint!r}")

        parsed = urlsplit(value)
        if parsed.scheme or parsed.netloc:
            base = urlsplit(self.base_url)
            if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
                raise ValueError(f"Absolute endpoint is outside the configured origin: {endpoint!r}")
            if hasattr(self._config, "validate_endpoint"):
                return self._config.validate_endpoint(value, purpose="HTTP request", allow_external=False)
            if parsed.username or parsed.password or parsed.fragment:
                raise ValueError(f"Invalid absolute endpoint: {endpoint!r}")
            return value

        if parsed.fragment:
            raise ValueError(f"Fragments are not allowed in HTTP endpoints: {endpoint!r}")
        base = urlsplit(self.base_url)
        base_path = base.path.rstrip("/")
        candidate_path = posixpath.normpath(f"{base_path}/{parsed.path.lstrip('/')}")
        if (
            base_path
            and candidate_path not in {base_path, f"{base_path}/"}
            and not candidate_path.startswith(f"{base_path}/")
        ):
            raise ValueError(f"Endpoint escapes the configured base path: {endpoint!r}")
        return urlunsplit((base.scheme, base.netloc, candidate_path, parsed.query, ""))

    @staticmethod
    def _is_sensitive_key(key: Any) -> bool:
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        return any(
            part in normalized
            for part in (
                "password",
                "passwd",
                "token",
                "secret",
                "authorization",
                "cookie",
                "clientid",
                "encryptkey",
                "appkey",
                "appsecret",
                "credential",
                "username",
                "phone",
                "email",
                "address",
                "idcard",
                "mobile",
                "identity",
                "realname",
                "contact",
                "account",
            )
        )

    @staticmethod
    def _redact(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: "[REDACTED]" if HttpDriver._is_sensitive_key(key) else HttpDriver._redact(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [HttpDriver._redact(item) for item in value]
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    @classmethod
    def _redact_text(cls, value: str) -> str:
        pattern = (
            r"(?i)([\"']?(?:password|passwd|token|secret|authorization|cookie|clientid|"
            r"encrypt[-_]?key|app[-_]?key|app[-_]?secret|credential|username|phone|email|"
            r"address|id[-_]?card|mobile|identity|realname|contact|account)[\"']?\s*[:=]\s*)"
            r"([\"']?)([^\"'&,\s}]+)"
        )
        return re.sub(pattern, r"\1\2[REDACTED]", value)

    @classmethod
    def _redact_url(cls, url: str) -> str:
        parsed = urlsplit(str(url))
        if not parsed.scheme or not parsed.netloc:
            return "[REDACTED URL]" if parsed.query else str(url)
        safe_netloc = parsed.hostname or parsed.netloc
        if parsed.port:
            safe_netloc = f"{safe_netloc}:{parsed.port}"
        query = "[REDACTED]" if parsed.query else ""
        return urlunsplit((parsed.scheme, safe_netloc, parsed.path, query, ""))

    def _log_request(self, method: str, url: str, **kwargs: Any) -> None:
        logger.debug(f"Request: {method} {self._redact_url(url)}")
        if "json" in kwargs:
            logger.debug(f"Request body: {json.dumps(self._redact(kwargs['json']), ensure_ascii=False, default=str)}")
        if "data" in kwargs:
            logger.debug(f"Request form data: {self._redact_text(str(self._redact(kwargs['data'])))}")
        if "params" in kwargs:
            logger.debug(
                f"Request params: {json.dumps(self._redact(kwargs['params']), ensure_ascii=False, default=str)}"
            )
        if "headers" in kwargs:
            logger.debug(
                f"Request headers: {json.dumps(self._redact(kwargs['headers']), ensure_ascii=False, default=str)}"
            )
        if "cookies" in kwargs:
            logger.debug(
                f"Request cookies: {json.dumps(self._redact(kwargs['cookies']), ensure_ascii=False, default=str)}"
            )

    def _log_response(self, response: requests.Response) -> None:
        logger.debug(f"Response status: {response.status_code}")
        elapsed = getattr(response, "elapsed", None)
        elapsed_seconds = elapsed.total_seconds() if elapsed is not None else 0.0
        logger.debug(f"Response time: {elapsed_seconds:.3f}s")
        try:
            body = response.json()
            logger.debug(f"Response body: {json.dumps(self._redact(body), ensure_ascii=False, indent=2)}")
        except (json.JSONDecodeError, ValueError):
            logger.debug("Response body omitted because it is not structured JSON")

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

from typing import Any

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.drivers.http_driver import HttpDriver


class APIClient:
    """Facade over HttpDriver for backward compatibility; exposes session and base_url."""

    def __init__(
        self, base_url: str | None = None, timeout: int | None = None, driver: HttpDriver | None = None
    ) -> None:
        config = get_config()
        if config is None:
            raise ValueError("Config manager not initialized")
        resolved_base = base_url or config.api_base_url
        self._driver = driver or HttpDriver(resolved_base, config)
        if timeout is not None:
            self._driver.timeout = timeout
        self.base_url = self._driver.base_url
        self.timeout = self._driver.timeout
        self.session = self._driver.session

    def _build_url(self, endpoint: str) -> str:
        return self._driver._build_url(endpoint)

    def request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
        return self._driver.request(method, endpoint, **kwargs)

    def get(self, endpoint: str, **kwargs: Any) -> Any:
        return self._driver.get(endpoint, **kwargs)

    def post(self, endpoint: str, **kwargs: Any) -> Any:
        return self._driver.post(endpoint, **kwargs)

    def put(self, endpoint: str, **kwargs: Any) -> Any:
        return self._driver.put(endpoint, **kwargs)

    def patch(self, endpoint: str, **kwargs: Any) -> Any:
        return self._driver.patch(endpoint, **kwargs)

    def delete(self, endpoint: str, **kwargs: Any) -> Any:
        return self._driver.delete(endpoint, **kwargs)

    def set_header(self, key: str, value: str) -> None:
        self.session.headers[key] = value

    def set_default_api_headers(self, *, content_type: str, clientid: str) -> None:
        self.session.headers["Content-Type"] = content_type
        self.session.headers["clientid"] = clientid

    def set_auth_token(self, token: str, token_type: str = "Bearer") -> None:
        self.session.headers["Authorization"] = f"{token_type} {token}"

    def clear_auth(self) -> None:
        self.session.headers.pop("Authorization", None)

    def close(self) -> None:
        self._driver.close()

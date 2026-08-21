"""Authentication facade for login."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import get_config, validate_environment
from modules.auto_test.core.logger import get_logger
from modules.auto_test.core.secret_manager import AuthConfig, get_secret_manager
from modules.auto_test.reporting.allure_http import attach_request_info, step

logger = get_logger()


class AuthFacade:
    def __init__(self, client: APIClient | None = None) -> None:
        self._client = client or APIClient()
        self._config = get_config()
        self._secrets = get_secret_manager()

    @property
    def client(self) -> APIClient:
        return self._client

    def _login_path(self) -> str:
        path = str(self._config.get("api.auth_login_path", "/oms-admin/auth/login")).strip()
        parsed = urlparse(path)
        if parsed.scheme or parsed.netloc or path.startswith("//") or parsed.query or parsed.fragment:
            raise ValueError("Authentication endpoint must be a relative path")
        if not path.startswith("/"):
            path = f"/{path}"
        if any(part == ".." for part in path.split("/")) or any(char in path for char in ("\\", "\r", "\n")):
            raise ValueError("Authentication endpoint may not escape the API base path")
        return path

    def get_auth_config(self, api_base_url: str | None = None, env: str | None = None) -> AuthConfig:
        return self._secrets.get_auth_config(api_base_url=api_base_url, env=env)

    def _origin_from_api_base(self, api_base: str) -> str:
        from urllib.parse import urlparse

        p = urlparse(api_base)
        return f"{p.scheme}://{p.netloc}"

    def build_login_headers(self, env: str | None = None) -> dict[str, str]:
        if env:
            validate_environment(env)
        ac = self._secrets.get_auth_config(api_base_url=self._config.api_base_url, env=env)
        return {
            "clientid": ac.clientid,
            "encrypt-key": ac.encrypt_key,
            "isencrypt": ac.isencrypt,
            "content-language": ac.content_language,
            "content-type": "application/json;charset=UTF-8",
            "accept": "application/json, text/plain, */*",
            "origin": ac.origin,
            "user-agent": ac.user_agent,
        }

    def apply_default_api_headers(self, env: str | None = None) -> None:
        if env:
            validate_environment(env)
        ac = self._secrets.get_auth_config(api_base_url=self._config.api_base_url, env=env)
        self._client.set_default_api_headers(
            content_type="application/json;charset=UTF-8",
            clientid=ac.clientid,
        )

    def login(
        self, username: str | None = None, password: str | None = None, env: str | None = None
    ) -> requests.Response:
        pwd_body = password if password else self._secrets.get_api_login_password_payload()
        path = self._login_path()
        headers = self.build_login_headers(env=env)
        logger.info("Auth login requested for configured endpoint path=%s", path)
        with step("用户登录"):
            resp = self._client.post(path, json={"password": pwd_body}, headers=headers)
            attach_request_info(resp)
        return resp

    def get_token(self, username: str | None = None, password: str | None = None, env: str | None = None) -> str:
        response = self.login(username, password, env=env)
        data: dict[str, Any] = response.json()
        if data.get("code") == 200:
            d = data.get("data") or {}
            token = d.get("token") or d.get("access_token")
            if token:
                logger.info("登录成功，获取 token 成功")
                return str(token)
            logger.error("登录成功，但未获取到 token")
            raise ValueError("登录成功，但未获取到token")
        logger.error("登录失败（服务端返回认证失败）")
        raise ValueError(f"登录失败: {data.get('msg')}")

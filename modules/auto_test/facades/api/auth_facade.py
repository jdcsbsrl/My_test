"""Authentication API as a harness facade (config + secrets + reporting)."""

from __future__ import annotations

from typing import Any

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger
from modules.auto_test.core.secret_manager import get_secret_manager
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
        return str(self._config.get("api.auth_login_path", "/oms-admin/auth/login"))

    def build_login_headers(self) -> dict[str, str]:
        ac = self._secrets.get_auth_config(api_base_url=self._config.api_base_url)
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
        ac = self._secrets.get_auth_config(api_base_url=self._config.api_base_url, env=env)
        self._client.set_default_api_headers(
            content_type="application/json;charset=UTF-8",
            clientid=ac.clientid,
        )

    def login(self, username: str | None = None, password: str | None = None) -> requests.Response:
        try:
            user = username or self._secrets.get_credentials().username
        except ValueError:
            user = username or "(set TEST_USERNAME for clearer logs)"
        pwd_body = password if password else self._secrets.get_api_login_password_payload()
        path = self._login_path()
        headers = self.build_login_headers()
        logger.info("Auth login for user=%s path=%s", user, path)
        with step("用户登录"):
            resp = self._client.post(path, json={"password": pwd_body}, headers=headers)
            attach_request_info(resp)
        return resp

    def get_token(self, username: str | None = None, password: str | None = None) -> str:
        response = self.login(username, password)
        data: dict[str, Any] = response.json()
        if data.get("code") == 200:
            d = data.get("data") or {}
            token = d.get("token") or d.get("access_token")
            if token:
                logger.info("登录成功，获取 token 成功")
                return str(token)
            logger.error("登录成功，但未获取到 token")
            raise ValueError("登录成功，但未获取到token")
        logger.error("登录失败: %s", data.get("msg"))
        raise ValueError(f"登录失败: {data.get('msg')}")

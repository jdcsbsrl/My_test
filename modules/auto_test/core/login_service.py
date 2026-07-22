import time
from typing import Any

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.logger import get_logger
from modules.auto_test.facades.auth_facade import AuthFacade

logger = get_logger()


class LoginService:
    _instance: "LoginService | None" = None

    def __new__(cls) -> "LoginService":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._token: str | None = None
        self._token_obtain_time: float | None = None
        self._token_expires_in: int = 7200
        self._last_login_response: dict[str, Any] | None = None

        self._client = APIClient()
        self._auth = AuthFacade(self._client)

    def login(self, force: bool = False, env: str | None = None) -> dict[str, Any]:
        if not force and self._token is not None and self._is_token_valid():
            logger.info("Token still valid, returning cached token")
            return self._build_response()

        logger.info("Attempting login to obtain token...")
        try:
            self._auth.apply_default_api_headers(env=env)
            response = self._auth.login()
            logger.info("Login response status: %s", response.status_code)
            # 仅记录响应状态码和业务 code，不记录响应体以保护敏感信息
            try:
                resp_data = response.json()
                resp_code = resp_data.get("code", "N/A")
                resp_msg = resp_data.get("msg", "N/A")
                logger.info("Login response code: %s, msg: %s", resp_code, resp_msg)
            except Exception:
                logger.info("Login response (body not parsed)")
            response.raise_for_status()
            data = resp_data

            self._last_login_response = data

            if data.get("code") == 200:
                d = data.get("data") or {}
                self._token = d.get("token") or d.get("access_token")
                self._token_obtain_time = time.time()
                logger.info("Login successful, token obtained")
                return self._build_response(success=True)
            error_msg = data.get("msg", "Unknown error")
            logger.error("Login failed: %s", error_msg)
            return self._build_response(success=False, error=error_msg)

        except requests.RequestException as e:
            logger.error("Login request failed: %s", str(e))
            return self._build_response(success=False, error=str(e))

    def _is_token_valid(self) -> bool:
        if self._token is None or self._token_obtain_time is None:
            return False
        elapsed = time.time() - self._token_obtain_time
        return elapsed < self._token_expires_in

    def _build_response(self, success: bool = True, error: str | None = None) -> dict[str, Any]:
        return {
            "success": success,
            "token": self._token if success else None,
            "error": error,
            "token_obtain_time": self._token_obtain_time,
            "is_token_valid": self._is_token_valid(),
        }

    def get_token(self, force_refresh: bool = False) -> str | None:
        result = self.login(force=force_refresh)
        if result["success"]:
            return str(result["token"])
        return None

    def get_login_response(self) -> dict[str, Any] | None:
        return self._last_login_response

    def is_logged_in(self) -> bool:
        return self._token is not None and self._is_token_valid()

    def clear_token(self) -> None:
        self._token = None
        self._token_obtain_time = None
        logger.info("Token cleared")

    def get_token_info(self) -> dict[str, Any]:
        return {
            "has_token": self._token is not None,
            "token_valid": self._is_token_valid(),
            "token_obtain_time": self._token_obtain_time,
            "elapsed_seconds": time.time() - self._token_obtain_time if self._token_obtain_time else None,
        }


def get_login_service() -> LoginService:
    return LoginService()

"""Backward-compatible import for the canonical authentication facade.

Authentication behavior is implemented in ``modules.auto_test.facades.auth_facade``.
This module remains as a compatibility path for existing API-layer imports.
"""

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.secret_manager import get_secret_manager
from modules.auto_test.facades.auth_facade import AuthFacade as _CanonicalAuthFacade
from modules.auto_test.reporting.allure_http import attach_request_info


class AuthFacade(_CanonicalAuthFacade):
    """Compatibility facade that preserves the API module's patch points."""

    def __init__(self, client: APIClient | None = None) -> None:
        self._client = client or APIClient()
        self._config = get_config()
        self._secrets = get_secret_manager()

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

    def login(self, username: str | None = None, password: str | None = None) -> requests.Response:
        try:
            user = username or self._secrets.get_credentials().username
        except ValueError:
            user = username or "(set TEST_USERNAME for clearer logs)"
        pwd_body = password if password else self._secrets.get_api_login_password_payload()
        response = self._client.post(
            self._login_path(),
            json={"password": pwd_body},
            headers=self.build_login_headers(),
        )
        attach_request_info(response)
        return response


__all__ = ["AuthFacade"]

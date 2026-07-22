import warnings
from typing import Any

from modules.auto_test.api.base_api import BaseAPI
from modules.auto_test.core.api_client import APIClient
from modules.auto_test.facades.auth_facade import AuthFacade


class AuthAPI(BaseAPI):
    """Deprecated: use AuthFacade."""

    def __init__(self, client: APIClient | None = None) -> None:
        super().__init__(client)
        warnings.warn(
            "AuthAPI is deprecated; use AuthFacade from modules.auto_test.facades.auth_facade.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._facade = AuthFacade(self.client)

    def login(self, username: str, password: str) -> Any:
        return self._facade.login(username, password)

    def get_token(self, username: str, password: str) -> str:
        return self._facade.get_token(username, password)

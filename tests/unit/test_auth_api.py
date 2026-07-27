from unittest.mock import Mock

import pytest

from modules.auto_test.api.auth_api import AuthAPI


pytestmark = pytest.mark.unit


def test_auth_api_login_delegates_to_facade(monkeypatch):
    client = Mock()
    facade = Mock()
    facade.login.return_value = {"token": "abc"}
    facade_cls = Mock(return_value=facade)
    monkeypatch.setattr("modules.auto_test.api.auth_api.AuthFacade", facade_cls)

    with pytest.warns(DeprecationWarning):
        api = AuthAPI(client)

    result = api.login("user", "pass")

    assert result == {"token": "abc"}
    facade_cls.assert_called_once_with(client)
    facade.login.assert_called_once_with("user", "pass")


def test_auth_api_get_token_delegates_to_facade(monkeypatch):
    client = Mock()
    facade = Mock()
    facade.get_token.return_value = "token-123"
    monkeypatch.setattr("modules.auto_test.api.auth_api.AuthFacade", Mock(return_value=facade))

    with pytest.warns(DeprecationWarning):
        api = AuthAPI(client)

    assert api.get_token("user", "pass") == "token-123"
    facade.get_token.assert_called_once_with("user", "pass")

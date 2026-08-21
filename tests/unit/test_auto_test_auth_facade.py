from types import SimpleNamespace

import pytest

from modules.auto_test.core.secret_manager import AuthConfig, Credentials
from modules.auto_test.facades.auth_facade import AuthFacade


pytestmark = pytest.mark.unit


class DummyClient:
    def __init__(self):
        self.default_headers = None
        self.post_calls = []

    def set_default_api_headers(self, **kwargs):
        self.default_headers = kwargs

    def post(self, path, json=None, headers=None):
        self.post_calls.append({"path": path, "json": json, "headers": headers})
        return SimpleNamespace(status_code=200, json=lambda: {"code": 200, "data": {"token": "token-1"}})


class DummySecrets:
    def __init__(self):
        self.auth_config = AuthConfig(
            clientid="client",
            encrypt_key="key",
            isencrypt="true",
            content_language="zh_CN",
            origin="https://erp.test",
            user_agent="pytest",
        )
        self.credentials = Credentials(username="alice", password="secret")

    def get_auth_config(self, api_base_url=None, env=None):
        return self.auth_config

    def get_credentials(self):
        return self.credentials

    def get_api_login_password_payload(self):
        return "encrypted-password"


@pytest.fixture
def facade(monkeypatch):
    config = SimpleNamespace(
        api_base_url="https://erp.test/api",
        get=lambda key, default=None: "/login" if key == "api.auth_login_path" else default,
    )
    secrets = DummySecrets()
    monkeypatch.setattr("modules.auto_test.facades.auth_facade.get_config", lambda: config)
    monkeypatch.setattr("modules.auto_test.facades.auth_facade.get_secret_manager", lambda: secrets)
    monkeypatch.setattr("modules.auto_test.facades.auth_facade.attach_request_info", lambda response: None)
    return AuthFacade(DummyClient())


def test_build_login_headers_uses_secret_auth_config(facade):
    headers = facade.build_login_headers(env="uat")

    assert headers == {
        "clientid": "client",
        "encrypt-key": "key",
        "isencrypt": "true",
        "content-language": "zh_CN",
        "content-type": "application/json;charset=UTF-8",
        "accept": "application/json, text/plain, */*",
        "origin": "https://erp.test",
        "user-agent": "pytest",
    }


def test_apply_default_api_headers_sets_client_defaults(facade):
    facade.apply_default_api_headers(env="uat")

    assert facade.client.default_headers == {
        "content_type": "application/json;charset=UTF-8",
        "clientid": "client",
    }


def test_login_posts_password_payload_without_real_network(facade):
    response = facade.login(env="uat")

    assert response.status_code == 200
    assert facade.client.post_calls == [
        {
            "path": "/login",
            "json": {"password": "encrypted-password"},
            "headers": facade.build_login_headers(env="uat"),
        }
    ]


def test_login_path_rejects_absolute_or_parent_paths(facade):
    facade._config.get = lambda key, default=None: "https://evil.example/login" if key == "api.auth_login_path" else default
    with pytest.raises(ValueError, match="relative path"):
        facade._login_path()

    facade._config.get = lambda key, default=None: "/../login" if key == "api.auth_login_path" else default
    with pytest.raises(ValueError, match="escape"):
        facade._login_path()


def test_get_token_accepts_token_and_access_token(monkeypatch, facade):
    facade.login = lambda username=None, password=None, env=None: SimpleNamespace(
        json=lambda: {"code": 200, "data": {"access_token": "access"}}
    )

    assert facade.get_token() == "access"


def test_get_token_raises_for_missing_token_or_failure(facade):
    facade.login = lambda username=None, password=None, env=None: SimpleNamespace(json=lambda: {"code": 200, "data": {}})
    with pytest.raises(ValueError):
        facade.get_token()

    facade.login = lambda username=None, password=None, env=None: SimpleNamespace(
        json=lambda: {"code": 401, "msg": "bad credentials"}
    )
    with pytest.raises(ValueError, match="bad credentials"):
        facade.get_token()

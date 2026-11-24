import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from fixtures import harness_plugin

pytestmark = pytest.mark.unit


class FakeConfig:
    def __init__(self, **options):
        self.options = options

    def getoption(self, name, default=None):
        return self.options.get(name, default)


class FakeRequest:
    def __init__(self, config):
        self.config = config


def test_root_configuration_loads_the_only_harness_entry_point():
    pytest_ini = Path(__file__).parents[2] / "pytest.ini"
    assert "-p fixtures.harness_plugin" in pytest_ini.read_text(encoding="utf-8")

    conftest = Path(__file__).parents[2] / "modules" / "auto_test" / "conftest.py"
    assert "pytest.fixture" not in conftest.read_text(encoding="utf-8")
    assert "pytest_configure" not in conftest.read_text(encoding="utf-8")


def test_authentication_fixtures_share_one_session_source():
    storage_state_params = inspect.signature(harness_plugin.authenticated_storage_state._fixture_function).parameters
    login_response_params = inspect.signature(harness_plugin.login_response._fixture_function).parameters

    assert list(storage_state_params) == ["_authenticated_session"]
    assert list(login_response_params) == ["_authenticated_session"]
    assert "ThreadPoolExecutor" not in Path(harness_plugin.__file__).read_text(encoding="utf-8")


def test_authentication_refresh_updates_shared_state_and_replaces_storage_atomically(tmp_path, monkeypatch):
    auth_file = tmp_path / "auth-state.json"
    auth_file.write_text(json.dumps({"cookies": [{"name": "old"}]}), encoding="utf-8")

    class FakeResponseRequest:
        def all_headers(self):
            return {"client-id": "refreshed-client"}

    class FakeResponse:
        url = "https://erp.test/auth/login"
        request = FakeResponseRequest()

        def json(self):
            return {"code": 200, "data": {"token": "refreshed-token"}}

    class FakeContext:
        def cookies(self):
            return [{"name": "session", "value": "refreshed", "domain": "erp.test", "path": "/"}]

        def storage_state(self, path):
            Path(path).write_text(json.dumps({"cookies": self.cookies()}), encoding="utf-8")

    class FakePage:
        def __init__(self):
            self.context = FakeContext()
            self.handlers = []
            self.removed = []

        def on(self, event, handler):
            assert event == "response"
            self.handlers.append(handler)

        def remove_listener(self, event, handler):
            self.removed.append((event, handler))

        def emit(self, response):
            for handler in self.handlers:
                handler(response)

    page = FakePage()

    class FakeLoginPage:
        def __init__(self, current_page):
            self.page = current_page

        def login(self, username, password):
            assert (username, password) == ("user", "password")
            self.page.emit(FakeResponse())
            return True

    monkeypatch.setattr(harness_plugin, "LoginPage", FakeLoginPage)
    monkeypatch.setattr(harness_plugin, "_assert_authenticated_page", lambda *args, **kwargs: None)
    monkeypatch.setattr(harness_plugin, "_capture_authentication_diagnostic", lambda *args, **kwargs: None)

    shared_response = {"code": 200, "data": {"token": "stale-token"}}
    state = {
        "storage_state": str(auth_file),
        "login_response": shared_response,
        "credentials": {"username": "user", "password": "password"},
        "refresh_lock": harness_plugin.threading.Lock(),
        "refresh_count": 0,
    }
    request = FakeRequest(SimpleNamespace())
    config_manager = SimpleNamespace(base_url="https://erp.test")

    harness_plugin._refresh_authenticated_session(
        state=state,
        page=page,
        request=request,
        config_manager=config_manager,
    )

    assert shared_response["data"]["token"] == "refreshed-token"
    assert shared_response["_clientid"] == "refreshed-client"
    assert shared_response["_cookies"][0]["value"] == "refreshed"
    assert json.loads(auth_file.read_text(encoding="utf-8"))["cookies"][0]["value"] == "refreshed"
    assert list(tmp_path.glob("*.refresh-*.tmp")) == []
    assert state["refresh_count"] == 1
    assert len(page.removed) == 1


def test_authentication_refresh_accepts_valid_session_after_login_ui_check_misses(tmp_path, monkeypatch):
    auth_file = tmp_path / "auth-state.json"
    auth_file.write_text(json.dumps({"cookies": []}), encoding="utf-8")

    class FakeRequestInfo:
        def all_headers(self):
            return {"clientid": "client"}

    class FakeResponse:
        url = "https://erp.test/auth/login"
        request = FakeRequestInfo()

        def json(self):
            return {"code": 200, "data": {"access_token": "fresh-token"}}

    class FakeContext:
        def cookies(self):
            return []

        def storage_state(self, path):
            Path(path).write_text(json.dumps({"cookies": []}), encoding="utf-8")

    class FakePage:
        def __init__(self):
            self.context = FakeContext()
            self.handlers = []

        def on(self, event, handler):
            self.handlers.append(handler)

        def remove_listener(self, event, handler):
            self.handlers.remove(handler)

    class FakeLoginPage:
        def __init__(self, page):
            self.page = page

        def login(self, username, password):
            for handler in self.page.handlers:
                handler(FakeResponse())
            return False

    authenticated_navigation = []
    monkeypatch.setattr(harness_plugin, "LoginPage", FakeLoginPage)
    monkeypatch.setattr(
        harness_plugin,
        "_assert_authenticated_page",
        lambda page, base_url, timeout: authenticated_navigation.append((base_url, timeout)),
    )
    monkeypatch.setattr(harness_plugin, "_capture_authentication_diagnostic", lambda *args, **kwargs: None)

    state = {
        "storage_state": str(auth_file),
        "login_response": {"code": 200, "data": {"token": "stale-token"}},
        "credentials": {"username": "user", "password": "password"},
        "refresh_lock": harness_plugin.threading.Lock(),
        "refresh_count": 0,
    }
    page = FakePage()

    harness_plugin._refresh_authenticated_session(
        state=state,
        page=page,
        request=FakeRequest(SimpleNamespace()),
        config_manager=SimpleNamespace(base_url="https://erp.test"),
    )

    assert authenticated_navigation == [("https://erp.test", 30000)]
    assert state["login_response"]["data"]["access_token"] == "fresh-token"
    assert state["refresh_count"] == 1


def test_apply_authenticated_state_refreshes_http_client_token_and_cookies():
    class FakeClient:
        def __init__(self):
            self.headers = {"Authorization": "Bearer stale", "clientid": "old-client"}
            self.cookies = requests.cookies.RequestsCookieJar()
            self.cookies.set("old-cookie", "old-value", domain="erp.test", path="/")

    client = FakeClient()
    login_response = {
        "data": {"token": "fresh-token"},
        "_clientid": "fresh-client",
        "_cookies": [{"name": "session", "value": "fresh-value", "domain": "erp.test", "path": "/"}],
    }

    harness_plugin._apply_authenticated_state_to_client(client, login_response)

    assert client.headers == {"Authorization": "Bearer fresh-token", "clientid": "fresh-client"}
    assert [(cookie.name, cookie.value) for cookie in client.cookies] == [("session", "fresh-value")]


def test_refresh_authenticated_http_client_forces_login_and_updates_api_state(monkeypatch):
    class FakeContext:
        cookies_cleared = False

        def clear_cookies(self):
            self.cookies_cleared = True

    class FakePage:
        context = FakeContext()
        evaluations = []

        def evaluate(self, expression):
            self.evaluations.append(expression)

    page = FakePage()
    state = {
        "login_response": {
            "data": {"token": "stale-token"},
            "_clientid": "stale-client",
            "_cookies": [],
        }
    }
    client = requests.Session()
    calls = []

    def refresh_session(**kwargs):
        calls.append(kwargs)
        kwargs["state"]["login_response"].update(
            {
                "data": {"token": "fresh-token"},
                "_clientid": "fresh-client",
                "_cookies": [{"name": "session", "value": "fresh-value", "domain": "erp.test", "path": "/"}],
            }
        )

    monkeypatch.setattr(harness_plugin, "_refresh_authenticated_session", refresh_session)
    refresh = harness_plugin.refresh_authenticated_http_client._fixture_function(
        FakeRequest(SimpleNamespace()),
        SimpleNamespace(base_url="https://erp.test"),
        state,
        page,
        client,
    )

    refresh()

    assert len(calls) == 1
    assert page.context.cookies_cleared
    assert page.evaluations == ["() => { window.localStorage.clear(); window.sessionStorage.clear(); }"]
    assert client.headers["Authorization"] == "Bearer fresh-token"
    assert client.headers["clientid"] == "fresh-client"
    assert [(cookie.name, cookie.value) for cookie in client.cookies] == [("session", "fresh-value")]
    client.close()


def test_authentication_refresh_cleans_temp_state_and_reports_failure(tmp_path, monkeypatch):
    auth_file = tmp_path / "auth-state.json"
    original = {"cookies": [{"name": "keep", "value": "original"}]}
    auth_file.write_text(json.dumps(original), encoding="utf-8")
    diagnostics = []

    class FakeContext:
        def storage_state(self, path):
            Path(path).write_text("partial", encoding="utf-8")
            raise OSError("disk full")

        def cookies(self):
            return []

    class FakePage:
        context = FakeContext()

        def on(self, event, handler):
            self.handler = handler

        def remove_listener(self, event, handler):
            pass

    class FakeLoginPage:
        def __init__(self, page):
            pass

        def login(self, username, password):
            return True

    monkeypatch.setattr(harness_plugin, "LoginPage", FakeLoginPage)
    monkeypatch.setattr(harness_plugin, "_assert_authenticated_page", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        harness_plugin,
        "_capture_authentication_diagnostic",
        lambda page, reason, config: diagnostics.append(reason),
    )

    state = {
        "storage_state": str(auth_file),
        "login_response": {"code": 200},
        "credentials": {"username": "user", "password": "password"},
        "refresh_lock": harness_plugin.threading.Lock(),
        "refresh_count": 0,
    }

    with pytest.raises(RuntimeError, match="认证刷新失败"):
        harness_plugin._refresh_authenticated_session(
            state=state,
            page=FakePage(),
            request=FakeRequest(SimpleNamespace()),
            config_manager=SimpleNamespace(base_url="https://erp.test"),
        )

    assert json.loads(auth_file.read_text(encoding="utf-8")) == original
    assert list(tmp_path.glob("*.refresh-*.tmp")) == []
    assert state["refresh_count"] == 0
    assert diagnostics == ["refresh-failure"]


def test_browser_entrypoints_share_one_driver_source():
    browser_params = inspect.signature(harness_plugin.browser._fixture_function).parameters
    driver_params = inspect.signature(harness_plugin.browser_driver_session._fixture_function).parameters

    assert list(browser_params) == ["_browser_driver"]
    assert list(driver_params) == ["_browser_driver"]


def test_browser_launch_options_only_override_config_when_cli_is_explicit():
    config = SimpleNamespace(
        invocation_params=SimpleNamespace(args=("--browser=firefox", "--headed", "--slow-mo", "25"))
    )
    request = FakeRequest(config)
    config_manager = SimpleNamespace(
        get=lambda key, default=None: {
            "playwright.browser": "chromium",
            "playwright.headless": True,
            "playwright.slow_mo": 0,
        }.get(key, default)
    )

    assert harness_plugin._browser_launch_options(request, config_manager) == {
        "browser": "firefox",
        "headless": False,
        "slow_mo": 25,
    }


def test_authorization_fails_closed_without_explicit_grant(monkeypatch):
    monkeypatch.delenv(harness_plugin.AUTHORIZATION_ENV_VAR, raising=False)
    manager = type("Manager", (), {"get_authorization_status": lambda self: {"authorized": False}})()
    monkeypatch.setattr(harness_plugin, "get_auth_manager", lambda: manager)

    with pytest.raises(Exception):
        harness_plugin._require_execution_authorization(FakeRequest(FakeConfig(**{"--skip-auth": False})))


def test_skip_auth_is_rejected_even_when_requested(monkeypatch):
    monkeypatch.setenv(harness_plugin.AUTHORIZATION_ENV_VAR, "approved")

    with pytest.raises(pytest.UsageError, match="skip-auth"):
        harness_plugin._require_execution_authorization(FakeRequest(FakeConfig(**{"--skip-auth": True})))


def test_authorization_requires_boolean_status_and_environment_grant(monkeypatch):
    monkeypatch.setenv(harness_plugin.AUTHORIZATION_ENV_VAR, "approved")
    manager = type("Manager", (), {"get_authorization_status": lambda self: {"authorized": "true"}})()
    monkeypatch.setattr(harness_plugin, "get_auth_manager", lambda: manager)

    with pytest.raises(Exception):
        harness_plugin._require_execution_authorization(FakeRequest(FakeConfig(**{"--skip-auth": False})))


def test_run_and_worker_paths_are_isolated(monkeypatch):
    monkeypatch.setattr(harness_plugin, "runtime_dir", lambda kind: Path(".runtime") / kind)
    monkeypatch.setenv("TEST_RUN_ID", "run-a")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    first = harness_plugin._runtime_reports_dir()

    monkeypatch.setenv("TEST_RUN_ID", "run-b")
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw1")
    second = harness_plugin._runtime_reports_dir()

    assert first != second
    assert first.parts[-2:] == ("run-a", "gw0")
    assert second.parts[-2:] == ("run-b", "gw1")


@pytest.mark.parametrize(
    "fixture_name, expected_scope",
    [
        ("browser", "session"),
        ("authenticated_storage_state", "session"),
        ("browser_driver_session", "session"),
        ("context", "function"),
        ("page", "function"),
        ("browser_page", "function"),
        ("http_client", "function"),
        ("login_token", "function"),
        ("authenticated_http_client", "function"),
        ("refresh_authenticated_http_client", "function"),
        ("api_client", "function"),
    ],
)
def test_resource_fixture_scopes_are_explicit(fixture_name, expected_scope):
    fixture = getattr(harness_plugin, fixture_name)
    assert fixture._fixture_function_marker.scope == expected_scope

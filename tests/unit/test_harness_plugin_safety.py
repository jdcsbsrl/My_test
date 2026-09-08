import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
        ("api_client", "function"),
    ],
)
def test_resource_fixture_scopes_are_explicit(fixture_name, expected_scope):
    fixture = getattr(harness_plugin, fixture_name)
    assert fixture._fixture_function_marker.scope == expected_scope

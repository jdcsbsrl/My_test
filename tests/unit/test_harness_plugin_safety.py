from pathlib import Path

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
        ("authenticated_http_client", "function"),
        ("api_client", "function"),
    ],
)
def test_resource_fixture_scopes_are_explicit(fixture_name, expected_scope):
    fixture = getattr(harness_plugin, fixture_name)
    assert fixture._fixture_function_marker.scope == expected_scope

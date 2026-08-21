from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.auto_test.drivers.http_driver import HttpDriver


pytestmark = pytest.mark.unit


class FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.setattr("modules.auto_test.drivers.http_driver.get_secret_manager", lambda: None)
    return HttpDriver(
        "https://erp.example.test/",
        FakeConfig({"api.timeout": 7, "api.retries": 1, "api.verify_ssl": False}),
    )


def test_init_configures_base_url_timeout_and_ssl(driver):
    assert driver.base_url == "https://erp.example.test"
    assert driver.timeout == 7
    assert driver.session.verify is False


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("/api/orders", "https://erp.example.test/api/orders"),
        ("api/orders", "https://erp.example.test/api/orders"),
    ],
)
def test_build_url_handles_relative_urls(driver, endpoint, expected):
    assert driver._build_url(endpoint) == expected


def test_build_url_rejects_cross_origin_absolute_url(driver):
    with pytest.raises(ValueError, match="outside the configured origin"):
        driver._build_url("https://external.example.test/orders")


def test_build_url_rejects_parent_path_escape(driver):
    with pytest.raises(ValueError, match="Unsafe endpoint path|escapes"):
        driver._build_url("../../etc/passwd")


def test_http_logs_redact_sensitive_values(driver, monkeypatch):
    messages = []
    monkeypatch.setattr("modules.auto_test.drivers.http_driver.logger.debug", messages.append)

    driver._log_request(
        "POST",
        "https://erp.example.test/api/login?token=secret",
        json={"username": "alice", "password": "pw", "nested": {"access_token": "jwt"}},
        headers={"Authorization": "Bearer jwt", "X-App-Key": "app-key", "X-App-Secret": "app-secret", "X-Trace": "ok"},
    )

    rendered = " ".join(messages)
    assert "pw" not in rendered
    assert "jwt" not in rendered
    assert "app-key" not in rendered
    assert "app-secret" not in rendered
    assert "[REDACTED]" in rendered
    assert "token=secret" not in rendered


def test_request_adds_default_timeout_and_returns_response(driver):
    response = Mock()
    response.status_code = 200
    response.elapsed = SimpleNamespace(total_seconds=lambda: 0.012)
    response.json.return_value = {"ok": True}
    driver.session.request = Mock(return_value=response)

    result = driver.request("GET", "/api/orders", params={"page": 1})

    assert result is response
    driver.session.request.assert_called_once_with(
        "GET",
        "https://erp.example.test/api/orders",
        params={"page": 1},
        timeout=7,
    )


def test_request_preserves_explicit_timeout(driver):
    response = Mock()
    response.status_code = 204
    response.elapsed = SimpleNamespace(total_seconds=lambda: 0.001)
    response.json.side_effect = ValueError
    response.text = ""
    driver.session.request = Mock(return_value=response)

    driver.post("/api/orders", json={"id": 1}, timeout=99)

    assert driver.session.request.call_args.kwargs["timeout"] == 99


def test_proxy_from_secret_manager_is_applied(monkeypatch):
    secret_manager = Mock()
    secret_manager.get_proxy.return_value = "http://proxy.example.test:8080"
    monkeypatch.setattr("modules.auto_test.drivers.http_driver.get_secret_manager", lambda: secret_manager)

    driver = HttpDriver("https://erp.example.test", FakeConfig())

    assert driver.session.proxies["http"] == "http://proxy.example.test:8080"
    assert driver.session.proxies["https"] == "http://proxy.example.test:8080"

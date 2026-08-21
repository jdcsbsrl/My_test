from __future__ import annotations

import pytest

from modules.auto_test.core.config_manager import ConfigManager


def test_ci_config_accepts_api_origin_and_adds_default_path(monkeypatch) -> None:
    monkeypatch.setenv("TEST_WEB_API_BASE_URL", "https://example.test")
    monkeypatch.setenv("TEST_WEB_BASE_URL", "https://example.test/oms-ui")

    config = ConfigManager._build_environment_config("test")

    assert config["origin"] == "https://example.test"
    assert config["base_url"] == "https://example.test/oms-ui"
    assert config["api_base_url"] == "https://example.test/oms-api"
    assert config["api"]["base_url"] == "https://example.test/oms-api"


def test_ci_config_accepts_full_api_url(monkeypatch) -> None:
    monkeypatch.setenv("TEST_WEB_API_BASE_URL", "https://example.test/oms-api")
    monkeypatch.setenv("TEST_WEB_BASE_URL", "https://example.test/oms-ui")

    config = ConfigManager._build_environment_config("test")

    assert config["origin"] == "https://example.test"
    assert config["api_base_url"] == "https://example.test/oms-api"


def test_invalid_origin_error_does_not_echo_value() -> None:
    with pytest.raises(ValueError, match=r"expected an HTTP\(S\) origin") as exc_info:
        ConfigManager._normalize_origin("***", field="origin")

    assert "***" not in str(exc_info.value)

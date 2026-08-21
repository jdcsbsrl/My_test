from __future__ import annotations

from tools.validate_ci_environment import main


def test_validator_accepts_api_and_ui_urls(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TEST_WEB_API_BASE_URL", "https://example.test/oms-api")
    monkeypatch.setenv("TEST_WEB_BASE_URL", "https://example.test/oms-ui")

    assert main([]) == 0
    output = capsys.readouterr().out
    assert "https://" not in output
    assert "path=/oms-api" in output
    assert "path=/oms-ui" in output


def test_validator_rejects_missing_api_url(monkeypatch, capsys) -> None:
    monkeypatch.delenv("TEST_WEB_API_BASE_URL", raising=False)

    assert main([]) == 1
    assert "TEST_WEB_API_BASE_URL is not configured" in capsys.readouterr().err


def test_validator_rejects_http_for_remote_host(monkeypatch, capsys) -> None:
    monkeypatch.setenv("TEST_WEB_API_BASE_URL", "http://example.test/oms-api")

    assert main([]) == 1
    assert "must use HTTPS" in capsys.readouterr().err

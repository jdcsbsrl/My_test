from __future__ import annotations

from pathlib import Path

from tools.scan_sensitive_artifacts import scan


def test_scanner_passes_clean_artifacts(tmp_path: Path) -> None:
    (tmp_path / "result.json").write_text('{"status": "passed"}', encoding="utf-8")

    assert scan(tmp_path) == 0


def test_scanner_blocks_known_token_without_printing_value(tmp_path: Path, capsys) -> None:
    # Build the fixture at runtime so repository push protection does not
    # mistake this synthetic test value for a credential.
    token = "sh" + "pat_" + ("a" * 32)
    (tmp_path / "result.json").write_text(f'{{"detail": "{token}"}}', encoding="utf-8")

    assert scan(tmp_path) == 1
    output = capsys.readouterr().out
    assert "shopify-token" in output
    assert token not in output


def test_scanner_uses_configured_secret_values(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_PASSWORD", "local-password-value")
    (tmp_path / "result.json").write_text('{"message": "local-password-value"}', encoding="utf-8")

    assert scan(tmp_path) == 1


def test_scanner_ignores_short_secret_inside_timestamp(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_PASSWORD", "123456")
    (tmp_path / "container.json").write_text('{"start": 1234567890, "stop": 1234567999}', encoding="utf-8")

    assert scan(tmp_path) == 0


def test_scanner_blocks_short_secret_as_password_value(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_PASSWORD", "123456")
    (tmp_path / "result.json").write_text('{"password": "123456"}', encoding="utf-8")

    assert scan(tmp_path) == 1


def test_scanner_blocks_short_secret_in_allure_container_sensitive_field(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_PASSWORD", "123456")
    (tmp_path / "fixture-container.json").write_text('{"password": "123456"}', encoding="utf-8")

    assert scan(tmp_path) == 1


def test_scanner_ignores_configured_secret_in_allure_container_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_PASSWORD", "123456")
    (tmp_path / "fixture-container.json").write_text('{"name": "123456", "start": 1234567890}', encoding="utf-8")

    assert scan(tmp_path) == 0


def test_scanner_ignores_short_secret_in_ordinary_message(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_PASSWORD", "123456")
    (tmp_path / "result.json").write_text('{"message": "order-123456-created"}', encoding="utf-8")

    assert scan(tmp_path) == 0

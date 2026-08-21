"""Shared logging helpers with recursive sensitive-data redaction."""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from loguru import logger

from modules.auto_test.core.config_manager import get_config

REDACTED_VALUE = "[REDACTED]"

_SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "authorization",
        "cookie",
        "clientid",
        "client_id",
        "encrypt_key",
        "app_key",
        "app_secret",
        "database_url",
        "api_key",
        "private_key",
        "refresh_token",
    }
)
_SENSITIVE_FIELD_PATTERN = (
    r"password|passwd|secret|token|access[-_.]?token|authorization|cookie|"
    r"client[-_.]?id|encrypt[-_.]?key|app[-_.]?(?:key|secret)|"
    r"database[-_.]?url|api[-_.]?key|private[-_.]?key|refresh[-_.]?token"
)
_SENSITIVE_ASSIGNMENT_PATTERN = re.compile(
    rf"(?i)(?P<prefix>(?<![\w-])(?P<key_quote>[\"']?)(?:{_SENSITIVE_FIELD_PATTERN})"
    r"(?P=key_quote)\s*[:=]\s*)"
    r"(?:(?P<value_quote>[\"'])(?P<quoted_value>.*?)(?P=value_quote)|"
    r"(?P<unquoted_value>[^\s,&}}]+))"
)
_URL_PATTERN = re.compile(r"(?i)https?://[^\s<>'\"`]+")
_URL_TRAILING_PUNCTUATION = ".,;:!?)]}"


def _normalize_field_name(key: Any) -> str:
    """Normalize common snake/kebab/camel-case field-name variants."""
    text = str(key)
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", text)
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _is_sensitive_field(key: Any) -> bool:
    normalized = _normalize_field_name(key)
    return any(normalized == name or normalized.endswith(f"_{name}") for name in _SENSITIVE_FIELD_NAMES)


def _redact_url_match(match: re.Match[str]) -> str:
    value = match.group(0)
    trailing = ""
    while value and value[-1] in _URL_TRAILING_PUNCTUATION:
        trailing = value[-1] + trailing
        value = value[:-1]

    parsed = urlsplit(value)
    if parsed.query or parsed.fragment:
        value = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    return value + trailing


def _redact_text(value: str) -> str:
    """Redact URL components and key/value pairs embedded in text."""
    redacted = _URL_PATTERN.sub(_redact_url_match, value)

    def replace_assignment(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        quote = match.group("value_quote")
        return prefix + (quote or "") + REDACTED_VALUE + (quote or "")

    return _SENSITIVE_ASSIGNMENT_PATTERN.sub(replace_assignment, redacted)


def redact_sensitive_data(value: Any) -> Any:
    """Recursively redact sensitive mapping fields and embedded sensitive text."""
    if isinstance(value, Mapping):
        return {
            key: REDACTED_VALUE if _is_sensitive_field(key) else redact_sensitive_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, set):
        return {redact_sensitive_data(item) for item in value}
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, bytes):
        return _redact_text(value.decode(errors="replace")).encode()
    if isinstance(value, bytearray):
        return bytearray(_redact_text(value.decode(errors="replace")).encode())
    return value


class _RedactedException(Exception):
    """Exception value used when a sink formats a Loguru traceback."""


def _redact_log_record(record: dict[str, Any]) -> None:
    """Sanitize the final Loguru record before it reaches any configured sink."""
    record["message"] = redact_sensitive_data(record.get("message", ""))
    record["extra"] = redact_sensitive_data(record.get("extra", {}))

    exception = record.get("exception")
    if exception is not None and getattr(exception, "value", None) is not None:
        safe_message = redact_sensitive_data(str(exception.value))
        record["exception"] = exception._replace(value=_RedactedException(safe_message), traceback=None)


logger.configure(patcher=_redact_log_record)


def setup_logger() -> None:
    config = get_config()
    log_level = config.get("log.level", "INFO")
    log_format = config.get(
        "log.format",
        "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    logs_dir = Path(__file__).parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)

    logger.remove()

    logger.add(
        sys.stdout,
        level=log_level,
        format=log_format,
        colorize=True,
    )

    logger.add(
        logs_dir / "test_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level=log_level,
        format=log_format,
        encoding="utf-8",
    )

    logger.add(
        logs_dir / "error_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        level="ERROR",
        format=log_format,
        encoding="utf-8",
    )


def get_logger():
    return logger

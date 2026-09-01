"""Allure steps and HTTP response attachments."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
import json
import re
from urllib.parse import urlsplit, urlunsplit

import allure
import requests

_SENSITIVE_KEY_PATTERN = (
    r"password|passwd|token|secret|authorization|cookie|clientid|encrypt[-_]key|"
    r"app[-_]?(?:key|secret)|api[-_]?key|credential|username|phone|email|address|"
    r"id[-_]?card|mobile|identity|realname|contact|account"
)


def _redact_text(value: str) -> str:
    pattern = rf"(?i)([\"']?(?:{_SENSITIVE_KEY_PATTERN})[\"']?\s*[:=]\s*)([\"']?)([^\"'&,\s}}]+)"
    return re.sub(pattern, r"\1\2[REDACTED]", value)


def _redact_url(value: str) -> str:
    parsed = urlsplit(str(value))
    if not parsed.scheme or not parsed.netloc:
        return "[REDACTED URL]" if parsed.query else str(value)
    safe_netloc = parsed.hostname or parsed.netloc
    if parsed.port:
        safe_netloc = f"{safe_netloc}:{parsed.port}"
    query = "[REDACTED]" if parsed.query else ""
    return urlunsplit((parsed.scheme, safe_netloc, parsed.path, query, ""))


def _redact_value(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if re.search(_SENSITIVE_KEY_PATTERN, str(key), re.IGNORECASE) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, bytes):
        return _redact_text(value.decode(errors="replace"))
    return value


def _safe_attachment(value, *, json_preferred: bool = True) -> tuple[str, str]:
    raw = value.decode(errors="replace") if isinstance(value, bytes) else str(value or "")
    if json_preferred:
        try:
            return json.dumps(_redact_value(json.loads(raw)), ensure_ascii=False, indent=2), "json"
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return ("[REDACTED NON-JSON CONTENT]" if raw else "[EMPTY]"), "text"


@contextmanager
def step(title: str) -> Generator[None, None, None]:
    with allure.step(title):
        yield


def attach_request_info(response: requests.Response) -> None:
    request = getattr(response, "request", None)
    if request is None:
        return
    allure.attach(
        request.method + " " + _redact_url(request.url),
        name="Request",
        attachment_type=allure.attachment_type.TEXT,
    )
    if request.body:
        body = request.body
        safe_body, body_type = _safe_attachment(body)
        allure.attach(
            safe_body,
            name="Request Body",
            attachment_type=(allure.attachment_type.JSON if body_type == "json" else allure.attachment_type.TEXT),
        )
    allure.attach(
        str(response.status_code),
        name="Response Status",
        attachment_type=allure.attachment_type.TEXT,
    )
    safe_response, response_type = _safe_attachment(response.text)
    allure.attach(
        safe_response,
        name="Response Body",
        attachment_type=(allure.attachment_type.JSON if response_type == "json" else allure.attachment_type.TEXT),
    )

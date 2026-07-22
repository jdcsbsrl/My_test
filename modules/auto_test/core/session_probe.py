"""Lightweight authenticated session checks (avoid heavy list APIs on large test stacks)."""

from __future__ import annotations

import json
from typing import Any

import requests

from modules.auto_test.core.api_client import APIClient
from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger

logger = get_logger()

_DEFAULT_GETINFO_PATHS: tuple[str, ...] = (
    "/oms-admin/getInfo",
    "/oms-admin/system/user/getInfo",
)


def assert_session_authenticated(
    client: APIClient,
    *,
    timeout_sec: float = 25.0,
) -> None:
    """Call a small GET (``getInfo`` family) to verify Bearer + gateway accept the session.

    **Why not ``batchListNew`` here:** on stacks like ``erptest``, the sales list can scan very
    large tables (dashboard ``queryTodoItems`` alone is often 10s+); ``batchListNew`` may exceed
    the default 30s HTTP timeout and is unsuitable for *login smoke* only.
    """
    cfg = get_config()
    paths: list[str] = []
    custom = cfg.get("api.session_probe_path")
    if custom:
        paths.append(str(custom))
    for p in _DEFAULT_GETINFO_PATHS:
        if p not in paths:
            paths.append(p)

    last_note = ""
    for path in paths:
        try:
            resp = client.get(path, timeout=timeout_sec)
            last_note = f"{path} HTTP {resp.status_code}"
            if resp.status_code == 401:
                continue
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            body: Any
            try:
                body = resp.json()
            except (json.JSONDecodeError, ValueError):
                logger.info("session probe: non-json 200 from {}", path)
                return
            if not isinstance(body, dict):
                continue
            code = body.get("code")
            if code == 401:
                continue
            if code in (200, 0):
                logger.info("session probe ok: {} (business code={})", path, code)
                return
            if code is None and ("user" in body or "roles" in body or "permissions" in body):
                logger.info("session probe ok: {} (legacy user payload)", path)
                return
            if body.get("user") is not None or body.get("data") is not None:
                inner = body.get("data")
                if isinstance(inner, dict) and (inner.get("user") is not None or inner.get("userId") is not None):
                    logger.info("session probe ok: {} (wrapped user)", path)
                    return
        except requests.RequestException as exc:
            last_note = f"{path}: {exc!r}"
            continue

    raise AssertionError(
        "会话探测失败：已尝试 getInfo 类轻量路径仍不可用。"
        "请在 configs 中设置 ``api.session_probe_path`` 指向本环境登录后可访问的 GET，"
        "或检查 token / 网关。最后记录：" + last_note
    )

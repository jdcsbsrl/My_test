"""Drive the real login UI and capture the browser's auth/login POST (headers + JSON body).

Used to obtain ``clientid``, ``encrypt-key``, and the encrypted ``password`` payload without
manually copying them into ``.env``.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import requests

if TYPE_CHECKING:
    from modules.auto_test.core.api_client import APIClient
from playwright.sync_api import Page, Request, Response, sync_playwright

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger

logger = get_logger()


def bearer_token_from_login_response(payload: dict[str, Any]) -> str | None:
    """Return session JWT from OMS login JSON (supports ``token`` or OAuth-style ``access_token``)."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    raw = data.get("token") or data.get("access_token")
    return str(raw) if raw else None


def jwt_payload_dict(token: str) -> dict[str, Any]:
    """Decode JWT payload (middle segment) without signature verification."""
    try:
        part = token.split(".")[1]
        padded = part + "=" * (-len(part) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        out = json.loads(raw.decode("utf-8"))
        return out if isinstance(out, dict) else {}
    except (IndexError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


@dataclass(frozen=True)
class CapturedAuthLoginRequest:
    """Material copied from the browser's login XHR for optional HTTP replay."""

    post_url: str
    request_headers: dict[str, str]
    json_body: dict[str, Any]
    clientid: str | None
    encrypt_key: str | None


def _login_page_url(ui_base_url: str) -> str:
    base = (ui_base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("UI base_url 为空：请检查 configs 中 base_url 或 TEST_WEB_BASE_URL。")
    if base.endswith("/login"):
        return base
    return f"{base}/login"


def _header_ci(headers: dict[str, str], name: str) -> str | None:
    lower = name.lower()
    for k, v in headers.items():
        if k.lower() == lower:
            return v
    return None


def _headers_for_requests_replay(raw: dict[str, str]) -> dict[str, str]:
    skip = {"content-length", "host", "connection"}
    out: dict[str, str] = {}
    for k, v in raw.items():
        if k.lower() in skip:
            continue
        out[k] = v
    return out


def _parse_login_json_body(request: Request) -> dict[str, Any]:
    data = request.post_data
    if not data or not data.strip():
        raise ValueError("登录请求体为空：无法解析加密密码（页面可能未发起 JSON 登录）。")
    try:
        body = json.loads(data)
    except json.JSONDecodeError:
        return {"password": data.strip()}
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        return {"password": body}
    raise ValueError("登录请求 JSON 根节点必须是对象或字符串。")


def _fill_login_form(page: Page, username: str, password: str) -> None:
    username_selectors = [
        "input[type='text']",
        "input[name='username']",
        "input[placeholder*='账号']",
        "input[placeholder*='手机号']",
    ]
    password_selectors = [
        "input[type='password']",
        "input[name='password']",
        "input[placeholder*='密码']",
    ]

    u_input = None
    for sel in username_selectors:
        loc = page.query_selector(sel)
        if loc and loc.is_visible():
            u_input = loc
            logger.info("login capture: username field ({})", sel)
            break
    if not u_input:
        raise RuntimeError("未找到用户名/手机号输入框，请更新选择器或检查登录页结构。")

    p_input = None
    for sel in password_selectors:
        loc = page.query_selector(sel)
        if loc and loc.is_visible():
            p_input = loc
            logger.info("login capture: password field ({})", sel)
            break
    if not p_input:
        raise RuntimeError("未找到密码输入框。")

    u_input.fill(username)
    p_input.fill(password)


def _click_login_button(page: Page) -> None:
    button_selectors = [
        "button[type='submit']",
        "button:has-text('登录')",
        ".el-button--primary",
        "form button",
    ]
    btn = None
    for sel in button_selectors:
        loc = page.query_selector(sel)
        if loc and loc.is_visible():
            btn = loc
            logger.info("login capture: submit ({})", sel)
            break
    if not btn:
        raise RuntimeError("未找到登录按钮。")
    btn.click()


def capture_auth_login_via_browser(
    *,
    ui_base_url: str,
    username: str,
    password: str,
    headless: bool | None = None,
    navigation_timeout_ms: int = 90_000,
    login_response_timeout_ms: int = 90_000,
) -> tuple[CapturedAuthLoginRequest, dict[str, Any]]:
    """Open the web login page, submit credentials, return captured POST + parsed JSON response.

    Raises:
        RuntimeError / ValueError: Page structure, timeout, or missing auth/login POST.
    """
    cfg = get_config()
    if headless is None:
        headless = bool(cfg.get("playwright.headless", True))

    login_url = _login_page_url(ui_base_url)
    logger.info("login capture: navigating {} headless={}", login_url, headless)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(navigation_timeout_ms)
            page.goto(login_url, wait_until="networkidle")

            def is_login_post(resp: Response) -> bool:
                try:
                    req = resp.request
                    return req.method == "POST" and "auth/login" in req.url
                except Exception:
                    return False

            _fill_login_form(page, username, password)

            with page.expect_response(
                lambda resp: is_login_post(resp),
                timeout=login_response_timeout_ms,
            ) as resp_info:
                _click_login_button(page)

            response = resp_info.value
            req = response.request
            raw_headers = dict(req.headers)
            body = _parse_login_json_body(req)
            captured = CapturedAuthLoginRequest(
                post_url=req.url,
                request_headers=_headers_for_requests_replay(raw_headers),
                json_body=body,
                clientid=_header_ci(raw_headers, "clientid"),
                encrypt_key=_header_ci(raw_headers, "encrypt-key"),
            )
            if not captured.clientid or not captured.encrypt_key:
                raise RuntimeError(
                    "已拦截 auth/login 请求，但缺少 clientid 或 encrypt-key 请求头；"
                    "请确认前端仍通过 HTTP 头发送这两项。"
                )

            try:
                payload = response.json()
            except Exception as exc:
                raise RuntimeError(f"无法解析登录接口 JSON 响应: {exc}") from exc
            if not isinstance(payload, dict):
                raise RuntimeError("登录响应 JSON 根节点必须是对象。")

            logger.info(
                "login capture: ok post_url={} clientid_prefix={}…",
                captured.post_url,
                (captured.clientid or "")[:4],
            )
            return captured, payload
        finally:
            browser.close()


def replay_captured_auth_login(
    captured: CapturedAuthLoginRequest,
    *,
    verify_ssl: bool | None = None,
    timeout_sec: int | None = None,
) -> requests.Response:
    """Replay the same JSON + headers with ``requests`` (proves capture is usable off-browser)."""
    cfg = get_config()
    if verify_ssl is None:
        verify_ssl = bool(cfg.get("api.verify_ssl", True))
    if timeout_sec is None:
        timeout_sec = int(cfg.get("api.timeout", 30))

    return requests.post(
        captured.post_url,
        headers=captured.request_headers,
        json=captured.json_body,
        timeout=timeout_sec,
        verify=verify_ssl,
    )


def authenticated_api_client_from_browser(
    *,
    profile: str,
    username: str,
    password: str,
) -> tuple[APIClient, CapturedAuthLoginRequest]:
    """Load YAML profile, browser-login once, return ``APIClient`` with Bearer + ``clientid``.

    Returns:
        Tuple of ``(api_client, captured_login_request)``. Caller must ``client.close()`` when done.
    """
    from modules.auto_test.core.api_client import APIClient
    from modules.auto_test.core.config_manager import ConfigManager, get_config

    ConfigManager._instance = None
    get_config(profile)
    cfg = get_config()
    captured, body = capture_auth_login_via_browser(
        ui_base_url=cfg.base_url,
        username=username,
        password=password,
    )
    token = bearer_token_from_login_response(body)
    if not token:
        raise RuntimeError("浏览器登录成功但未解析到 access_token / token")
    if not captured.clientid:
        raise RuntimeError("拦截到的登录请求缺少 clientid 请求头")

    client = APIClient()
    client.set_default_api_headers(
        content_type="application/json;charset=UTF-8",
        clientid=str(captured.clientid),
    )
    client.set_auth_token(str(token))
    return client, captured

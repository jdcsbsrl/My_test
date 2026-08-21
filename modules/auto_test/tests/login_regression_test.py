"""Login regression capture with secrets-free runtime reporting."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import pytest

from modules.trae_test.utils.runtime_paths import runtime_dir

load_dotenv()

USERNAME = os.getenv("TEST_USERNAME")
PASSWORD = os.getenv("TEST_PASSWORD")

_ENV_BASE_URLS = {
    "UAT": os.getenv("UAT_WEB_BASE_URL"),
    "TEST": os.getenv("TEST_WEB_BASE_URL"),
}

_missing = [k for k, v in _ENV_BASE_URLS.items() if not v]
if _missing:
    pytest.skip(f"缺少登录捕获环境变量: {_missing}", allow_module_level=True)

ENVIRONMENTS = {
    "UAT": {"ui_base_url": _ENV_BASE_URLS["UAT"], "login_endpoint": "auth/login"},
    "TEST": {"ui_base_url": _ENV_BASE_URLS["TEST"], "login_endpoint": "auth/login"},
}


def _safe_endpoint_path(value: Any) -> str:
    """Return only a URL path, never a query, fragment, or credential-bearing URL."""
    if not isinstance(value, str) or not value:
        return "[unavailable]"
    if value in {"[redacted]", "[unavailable]"}:
        return value

    try:
        parsed = urlsplit(value)
    except ValueError:
        return "[redacted]"

    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        return "[redacted]"
    if parsed.path.startswith("/"):
        return parsed.path
    return "[unavailable]"


def _response_code(response: Any) -> int | str | None:
    """Return a primitive response code without retaining or formatting the response body."""
    code = response.get("code") if isinstance(response, dict) else response
    if isinstance(code, bool):
        return None
    if isinstance(code, int):
        return code
    if isinstance(code, str) and code.isdigit() and len(code) <= 16:
        return code
    return None


def _response_succeeded(response: Any) -> bool:
    """Summarize login response success without exposing response contents."""
    return isinstance(response, dict) and (response.get("code") == 200 or response.get("success") is True)


def _safe_error_type(value: Any) -> str:
    """Keep only a Python exception class name in the report."""
    return value if isinstance(value, str) and value.isidentifier() else "UnknownError"


def run_login_capture(env_name: str, ui_base_url: str) -> dict:
    """Capture login data in memory and return only a safe execution summary."""
    from modules.auto_test.core.playwright_login_capture import capture_auth_login_via_browser

    print(f"\n[{env_name}] Starting login capture...")

    try:
        captured, response = capture_auth_login_via_browser(
            ui_base_url=ui_base_url,
            username=USERNAME,
            password=PASSWORD,
            headless=True,
            navigation_timeout_ms=90000,
            login_response_timeout_ms=90000,
        )

        result = {
            "env": env_name,
            "status": "success",
            "clientid_present": bool(captured.clientid),
            "encrypt_key_present": bool(captured.encrypt_key),
            "login_path": _safe_endpoint_path(captured.post_url),
            "response_code": _response_code(response),
            "response_success": _response_succeeded(response),
        }

        print(
            f"[{env_name}] SUCCESS: auth headers captured "
            f"(clientid={'yes' if result['clientid_present'] else 'no'}, "
            f"encrypt-key={'yes' if result['encrypt_key_present'] else 'no'}); "
            f"response_success={'yes' if result['response_success'] else 'no'}; "
            f"login_path={result['login_path']}"
        )
        return result

    except Exception as e:
        error_type = type(e).__name__
        print(f"[{env_name}] FAILED: {error_type}")
        return {
            "env": env_name,
            "status": "failed",
            "error_type": error_type,
            "clientid_present": False,
            "encrypt_key_present": False,
            "login_path": "[unavailable]",
        }


def generate_report(results: list[dict], timestamp: str) -> Path:
    """Generate a secrets-free JSON report under the unified runtime directory."""
    report_dir = runtime_dir("reports")

    report = {
        "test_type": "login_regression",
        "timestamp": timestamp,
        "environments": {},
        "summary": {
            "total": len(results),
            "success": sum(1 for r in results if r["status"] == "success"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
        },
    }

    for result in results:
        env_name = result["env"]
        report["environments"][env_name] = {
            "status": result["status"],
            "auth_summary": {
                "required_headers_present": bool(result.get("clientid_present"))
                and bool(result.get("encrypt_key_present")),
                "login_path": _safe_endpoint_path(result.get("login_path")),
                "response_code": _response_code(result.get("response_code")),
                "response_success": bool(result.get("response_success")),
            },
        }
        if result["status"] == "failed":
            report["environments"][env_name]["error_type"] = _safe_error_type(result.get("error_type"))

    report_path = report_dir / f"login_regression_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report saved: {report_path}")
    return report_path


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 60)
    print("Login Regression Test - Auth Parameter Capture")
    print("=" * 60)
    print(f"Timestamp: {timestamp}")

    results = []
    for env_name, config in ENVIRONMENTS.items():
        result = run_login_capture(env_name, config["ui_base_url"])
        results.append(result)

    report_path = generate_report(results, timestamp)

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for result in results:
        status_icon = "✓" if result["status"] == "success" else "✗"
        print(f"{status_icon} [{result['env']}] {result['status'].upper()}")
        if result["status"] == "success":
            print(
                f"    Auth summary: clientid={'present' if result['clientid_present'] else 'missing'}, "
                f"encrypt-key={'present' if result['encrypt_key_present'] else 'missing'}, "
                f"response_success={'yes' if result['response_success'] else 'no'}"
            )
    print("=" * 60)
    print(f"Report: {report_path}")

    return all(r["status"] == "success" for r in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

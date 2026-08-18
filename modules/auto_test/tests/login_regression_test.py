"""Login Regression Test - Capture auth parameters from UAT and TEST environments."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import pytest

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


def run_login_capture(env_name: str, ui_base_url: str) -> dict:
    """Capture auth params by performing browser login."""
    from modules.auto_test.core.playwright_login_capture import capture_auth_login_via_browser

    print(f"\n{'='*60}")
    print(f"[{env_name}] Starting login capture...")
    print(f"[{env_name}] UI URL: {ui_base_url}")
    print(f"{'='*60}")

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
            "clientid": captured.clientid,
            "encrypt_key": captured.encrypt_key,
            "post_url": captured.post_url,
            "response_success": response.get("code") == 200 or response.get("success") is True,
            "response_message": response.get("message", ""),
        }

        print(f"[{env_name}] SUCCESS!")
        print(f"[{env_name}] ClientID: {captured.clientid[:8]}...")
        print(f"[{env_name}] EncryptKey: {captured.encrypt_key[:20]}...")
        return result

    except Exception as e:
        print(f"[{env_name}] FAILED: {e}")
        return {
            "env": env_name,
            "status": "failed",
            "error": str(e),
            "clientid": None,
            "encrypt_key": None,
        }


def update_env_file(results: list[dict]) -> None:
    """Update .env file with captured auth parameters."""
    env_path = Path(__file__).parent.parent / ".env"

    updates = {}
    for result in results:
        if result["status"] != "success":
            continue
        env_key = result["env"].upper()
        prefix = f"TEST_{env_key}_"
        updates[f"{prefix}CLIENTID"] = result["clientid"]
        updates[f"{prefix}ENCRYPT_KEY"] = result["encrypt_key"]

    lines = env_path.read_text(encoding="utf-8").splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        skip = False
        for key in updates:
            if stripped.startswith(f"{key}="):
                skip = True
                break
        if skip:
            continue
        new_lines.append(line)
        if stripped.startswith("# TEST 环境认证配置") and "TEST_TEST_CLIENTID" not in updates:
            new_lines.append(f"TEST_TEST_CLIENTID={updates.get('TEST_TEST_CLIENTID', '')}")
            new_lines.append(f"TEST_TEST_ENCRYPT_KEY={updates.get('TEST_TEST_ENCRYPT_KEY', '')}")
        if stripped.startswith("# UAT 环境认证配置") and "TEST_UAT_CLIENTID" not in updates:
            new_lines.append(f"TEST_UAT_CLIENTID={updates.get('TEST_UAT_CLIENTID', '')}")
            new_lines.append(f"TEST_UAT_ENCRYPT_KEY={updates.get('TEST_UAT_ENCRYPT_KEY', '')}")

    for key, value in updates.items():
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print("\n.env file updated with auth parameters")


def generate_report(results: list[dict], timestamp: str) -> Path:
    """Generate test report JSON."""
    report_dir = Path(__file__).parent.parent / "reports"
    report_dir.mkdir(exist_ok=True)

    report = {
        "test_type": "login_regression",
        "timestamp": timestamp,
        "test_account": {"username": USERNAME, "password": "***"},
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
            "ui_url": ENVIRONMENTS[env_name]["ui_base_url"],
            "clientid": result.get("clientid"),
            "encrypt_key": result.get("encrypt_key"),
            "post_url": result.get("post_url"),
        }
        if result["status"] == "failed":
            report["environments"][env_name]["error"] = result.get("error", "Unknown error")

    report_path = report_dir / f"login_regression_{timestamp}.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Report saved: {report_path}")
    return report_path


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    print("=" * 60)
    print("Login Regression Test - Auth Parameter Capture")
    print("=" * 60)
    print(f"Username: {USERNAME}")
    print(f"Timestamp: {timestamp}")

    results = []
    for env_name, config in ENVIRONMENTS.items():
        result = run_login_capture(env_name, config["ui_base_url"])
        results.append(result)

    update_env_file(results)

    report_path = generate_report(results, timestamp)

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    for result in results:
        status_icon = "✓" if result["status"] == "success" else "✗"
        print(f"{status_icon} [{result['env']}] {result['status'].upper()}")
        if result["status"] == "success":
            print(f"    ClientID: {result['clientid'][:12]}...")
            print(f"    EncryptKey: {result['encrypt_key'][:24]}...")
    print("=" * 60)
    print(f"Report: {report_path}")

    return all(r["status"] == "success" for r in results)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

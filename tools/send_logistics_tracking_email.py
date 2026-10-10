#!/usr/bin/env python3
"""Email a private daily report without publishing it as an Actions artifact."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.auto_test.core.logistics_tracking_email import build_message, latest_result, send_qq_message


def main() -> int:
    values = dotenv_values(ROOT / ".env")
    address = os.environ.get("REPORT_EMAIL_TO") or values.get("REPORT_EMAIL_TO") or ""
    authorization_code = os.environ.get("QQ_SMTP_AUTH_CODE") or values.get("QQ_SMTP_AUTH_CODE") or ""
    if not re.fullmatch(r"[^@\s]+@qq\.com", address, flags=re.IGNORECASE) or not authorization_code:
        print("QQ email settings are incomplete", file=sys.stderr)
        return 2
    report, sheet = latest_result(ROOT)
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = f"https://github.com/{repository}/actions/runs/{run_id}" if repository and run_id else ""
    try:
        message = build_message(address, report, sheet, run_url=run_url)
        send_qq_message(message, address, authorization_code)
    except Exception as exc:
        # The report, SMTP server and parser could echo private data in exceptions.
        print(f"QQ report email failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    print("QQ SMTP accepted the daily report email")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

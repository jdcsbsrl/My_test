"""Run the sensitive-artifact scanner when runtime reports exist."""

from __future__ import annotations

import sys

from modules.trae_test.utils.runtime_paths import runtime_dir

try:
    from tools.scan_sensitive_artifacts import scan
except ModuleNotFoundError:  # pragma: no cover - direct pre-commit script execution
    from scan_sensitive_artifacts import scan


def main() -> int:
    reports = runtime_dir("reports", create=False)
    if not reports.exists():
        print("[OK] no runtime reports directory; sensitive-artifact scan skipped")
        return 0
    return scan(reports)


if __name__ == "__main__":
    sys.exit(main())

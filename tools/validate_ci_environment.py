"""Validate CI endpoint variables without printing secret values."""

from __future__ import annotations

import argparse
import os
import sys
from urllib.parse import urlsplit


def _validate(name: str, *, required: bool) -> bool:
    value = os.getenv(name, "").strip()
    if not value:
        if required:
            print(f"[ERROR] {name} is not configured", file=sys.stderr)
            return False
        print(f"[INFO] {name} is not configured (optional)")
        return True

    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print(f"[ERROR] {name} must be an HTTP(S) URL with a hostname", file=sys.stderr)
        return False
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        print(f"[ERROR] {name} must not contain credentials, query parameters, or fragments", file=sys.stderr)
        return False
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        print(f"[ERROR] {name} must use HTTPS outside localhost", file=sys.stderr)
        return False

    path = parsed.path or "/"
    print(f"[OK] {name}: scheme={parsed.scheme}, path={path}")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-ui", action="store_true", help="require TEST_WEB_BASE_URL")
    args = parser.parse_args(argv)
    valid = _validate("TEST_WEB_API_BASE_URL", required=True)
    valid = _validate("TEST_WEB_BASE_URL", required=args.require_ui) and valid
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())

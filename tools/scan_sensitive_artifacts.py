"""Scan generated artifacts for credentials and other sensitive values.

The scanner is intentionally dependency-free so it can run immediately after
pytest in GitHub Actions.  It reports only file names and rule names; matched
values are never written to stdout or stderr.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


MAX_FILE_SIZE = 10 * 1024 * 1024
TEXT_SUFFIXES = {
    ".json",
    ".log",
    ".txt",
    ".xml",
    ".html",
    ".htm",
    ".csv",
    ".md",
    ".yaml",
    ".yml",
    ".properties",
}

SECRET_ENV_NAMES = {
    "TEST_PASSWORD",
    "TEST_USERNAME",
    "TEST_TOKEN",
    "TEST_ACCESS_TOKEN",
    "TEST_REFRESH_TOKEN",
    "TEST_COOKIE",
    "TEST_WEBHOOK_SECRET",
}

PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("github-token", re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_\-]{20,}\b")),
    ("shopify-token", re.compile(r"\bshpat_[A-Za-z0-9_\-]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")),
    (
        "authorization-header",
        re.compile(r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*bearer\s+[A-Za-z0-9._\-+/=]{16,}"),
    ),
    (
        "secret-assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|access[_-]?token|refresh[_-]?token|api[_-]?key|cookie)\b"
            r"\s*[=:]\s*[\"']?[^\s\"',}]{8,}"
        ),
    ),
)


def _read_text(path: Path) -> str | None:
    """Read a reasonably sized text artifact, skipping binary files."""

    try:
        if path.stat().st_size > MAX_FILE_SIZE or path.suffix.lower() not in TEXT_SUFFIXES:
            return None
        raw = path.read_bytes()
    except OSError as exc:
        print(f"[ERROR] unable to read artifact: {path} ({exc})", file=sys.stderr)
        return None
    if b"\x00" in raw:
        return None
    return raw.decode("utf-8", errors="replace")


def _environment_values() -> tuple[str, ...]:
    values = {
        value.strip()
        for name, value in os.environ.items()
        if name.upper() in SECRET_ENV_NAMES and value.strip()
    }
    return tuple(value for value in values if len(value) >= 4)


def scan(root: Path) -> int:
    """Scan *root* recursively and return a process-style exit code."""

    if not root.exists():
        print(f"[ERROR] artifact path does not exist: {root}", file=sys.stderr)
        return 2
    if not root.is_dir():
        print(f"[ERROR] artifact path is not a directory: {root}", file=sys.stderr)
        return 2

    environment_values = _environment_values()
    findings: list[tuple[Path, str]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        text = _read_text(path)
        if text is None:
            continue
        rules = {rule for rule, pattern in PATTERNS if pattern.search(text)}
        if any(value in text for value in environment_values):
            rules.add("configured-secret-value")
        for rule in sorted(rules):
            findings.append((path, rule))

    if findings:
        print(f"[FAIL] sensitive values detected in {len({path for path, _ in findings})} artifact(s):")
        for path, rule in findings:
            print(f"  - {path}: {rule}")
        print("[FAIL] matched values were intentionally omitted from this output.")
        return 1

    print(f"[OK] no sensitive values detected under {root}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="directory containing generated artifacts")
    args = parser.parse_args()
    return scan(args.path)


if __name__ == "__main__":
    raise SystemExit(main())

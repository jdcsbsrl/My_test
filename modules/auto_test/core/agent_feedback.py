"""Append-only failure capture for Agent feedback loop (human triage → failure_cases.md)."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from modules.auto_test.core.agent_loader import repo_root


def _auto_log_path() -> Path:
    return repo_root() / ".agents" / "failure_auto_log.md"


def append_auto_failure_record(report: Any) -> None:
    """Write one line to failure_auto_log.md (not a substitute for curated Hashimoto lines)."""
    root = repo_root()
    path = _auto_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    excerpt = ""
    try:
        lr = getattr(report, "longrepr", "")
        excerpt = str(lr).replace("\n", " ")[:400]
    except Exception:
        excerpt = "(no longrepr)"

    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    nodeid = getattr(report, "nodeid", "?")
    line = f"[{stamp}] pytest_fail | {nodeid} | {excerpt}\n"

    with path.open("a", encoding="utf-8") as f:
        f.write(line)

    suggest = (
        f"Recorded failure under {path.relative_to(root)} — "
        "triage then add a Hashimoto line to .agents/failure_cases.md and update .agents/linter_rules.md if new pattern."
    )
    os.environ["_AGENT_LAST_FEEDBACK_HINT"] = suggest

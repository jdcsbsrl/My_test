"""Quantifiable harness observability: per-test outcomes and durations (JSONL)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, TextIO


def metrics_enabled() -> bool:
    return os.getenv("HARNESS_METRICS", "").lower() in ("1", "true", "yes")


def default_metrics_path(root: Path) -> Path:
    return root / "reports" / "harness_metrics" / "events.jsonl"


class HarnessMetricsRecorder:
    """Append-only JSONL sink (Chrome-trace-style offline analysis; not a full APM)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._started = time.time()

    def write_event(self, event: dict[str, Any], *, stream: TextIO | None = None) -> None:
        line = json.dumps(event, ensure_ascii=False)
        if stream is not None:
            stream.write(line + "\n")
            stream.flush()
            return
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def session_start(self, *, pytest_version: str, cwd: str) -> None:
        self.write_event(
            {
                "type": "session_start",
                "ts": time.time(),
                "pytest_version": pytest_version,
                "cwd": cwd,
                "harness": "auto_test",
            }
        )

    def test_call_report(
        self,
        *,
        nodeid: str,
        outcome: str,
        duration: float | None,
        keywords: list[str] | None = None,
    ) -> None:
        self.write_event(
            {
                "type": "test_call",
                "ts": time.time(),
                "nodeid": nodeid,
                "outcome": outcome,
                "duration_sec": duration,
                "keywords": keywords or [],
            }
        )

    def session_end(self, *, exitstatus: int) -> None:
        self.write_event(
            {
                "type": "session_end",
                "ts": time.time(),
                "exitstatus": exitstatus,
                "wall_sec": round(time.time() - self._started, 3),
            }
        )

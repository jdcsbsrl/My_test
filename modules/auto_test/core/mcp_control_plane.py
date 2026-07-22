"""Manual Control Plane: human gates and CI-safe bypass for oversight."""

from __future__ import annotations

import logging
import os
import sys
from typing import TextIO

logger = logging.getLogger(__name__)


def _skip_manual() -> bool:
    if os.getenv("AGENT_SKIP_MANUAL_GATE", "").lower() in ("1", "true", "yes"):
        return True
    if os.getenv("CI", "").lower() in ("1", "true", "yes"):
        return True
    return False


def manual_gate(prompt: str, *, stream: TextIO = sys.stderr) -> bool:
    """
    If AGENT_MANUAL_GATE=1 and not in CI / AGENT_SKIP_MANUAL_GATE, block until operator confirms.

    Returns True when proceeding is allowed; False if stdin EOF / non-interactive abort.
    """
    if os.getenv("AGENT_MANUAL_GATE", "").lower() not in ("1", "true", "yes"):
        return True
    if _skip_manual():
        logger.info("manual_gate: skipped (%s)", prompt[:200])
        return True
    if not sys.stdin.isatty():
        logger.warning("manual_gate: non-interactive stdin; auto-approve with warning")
        return True
    stream.write(f"\n[MANUAL GATE] {prompt}\nType ENTER to continue (or Ctrl+C to abort): ")
    stream.flush()
    try:
        sys.stdin.readline()
    except OSError:
        return False
    return True

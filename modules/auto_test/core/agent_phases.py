"""Agent session phases: initialization (planning) vs coding (implementation)."""

from __future__ import annotations

import os

PHASE_INITIALIZATION = "initialization"
PHASE_CODING = "coding"
_VALID = frozenset({PHASE_INITIALIZATION, PHASE_CODING})


def resolve_agent_phase() -> str:
    """Resolve phase from AGENT_PHASE; default coding for harness compatibility."""
    raw = (os.getenv("AGENT_PHASE") or PHASE_CODING).strip().lower()
    if raw in ("init", "initialization", "plan", "planning"):
        return PHASE_INITIALIZATION
    if raw in ("code", "coding", "implement", "implementation"):
        return PHASE_CODING
    return PHASE_CODING if raw not in _VALID else raw

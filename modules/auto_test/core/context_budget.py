"""Heuristic context window utilization (default cap 40%)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_WINDOW_TOKENS = 128_000
DEFAULT_MAX_RATIO = 0.4


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class ContextBudget:
    """Track estimated token usage against a synthetic window (Smart vs Dumb zone hints)."""

    window_tokens: int = field(
        default_factory=lambda: int(os.getenv("CONTEXT_WINDOW_TOKENS", str(DEFAULT_WINDOW_TOKENS)))
    )
    max_ratio: float = field(
        default_factory=lambda: float(os.getenv("CONTEXT_BUDGET_MAX_RATIO", str(DEFAULT_MAX_RATIO)))
    )
    _components: dict[str, int] = field(default_factory=dict)

    def record(self, component: str, text: str) -> int:
        n = _estimate_tokens(text)
        self._components[component] = n
        return n

    def estimated_tokens(self) -> int:
        return sum(self._components.values())

    def current_ratio(self) -> float:
        if self.window_tokens <= 0:
            return 0.0
        return min(1.0, self.estimated_tokens() / float(self.window_tokens))

    def is_over_budget(self) -> bool:
        return self.current_ratio() > self.max_ratio + 1e-9

    def advisory_message(self) -> str | None:
        r = self.current_ratio()
        if r <= self.max_ratio:
            return None
        return (
            f"context_budget: estimated {r:.1%} of window ({self.estimated_tokens()} tok est.) "
            f"exceeds max {self.max_ratio:.0%}; prune prompts or defer to scripts (Dumb Zone)"
        )


def defer_to_dumb_zone(reason: str) -> str:
    """Return a standard hint to push work to deterministic tooling."""
    return f"Dumb Zone: run pytest/agent_linter/e2e scripts instead of expanding context — {reason}"

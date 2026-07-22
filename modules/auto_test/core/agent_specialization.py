"""Agent specialization: domain-scoped knowledge (minimal irrelevant context)."""

from __future__ import annotations

import os

DOMAIN_FULL = "full"
DOMAIN_CORE = "core"
DOMAIN_SALES_API = "sales_api"
DOMAIN_SALES_UI = "sales_ui"

_ALL = frozenset({DOMAIN_FULL, DOMAIN_CORE, DOMAIN_SALES_API, DOMAIN_SALES_UI})


def resolve_agent_domain() -> str:
    """
    AGENT_DOMAIN selects which manifest entries apply (Smart Zone focus).

    - full: no domain filtering (widest set; default for backward compatibility).
    - core: harness / policy / generic testing docs only (excludes domain-tagged KB noise).
    - sales_api | sales_ui: core-global entries plus entries tagged for that domain.
    """
    raw = (os.getenv("AGENT_DOMAIN") or DOMAIN_FULL).strip().lower()
    aliases = {
        "api": DOMAIN_SALES_API,
        "ui": DOMAIN_SALES_UI,
        "platform": DOMAIN_CORE,
        "harness": DOMAIN_CORE,
    }
    raw = aliases.get(raw, raw)
    if raw not in _ALL:
        return DOMAIN_FULL
    return raw


def domain_accepts(domain: str, entry_domains: list[str] | None) -> bool:
    """Manifest row filter: None => available to all non-full filters; full always passes."""
    if domain == DOMAIN_FULL:
        return True
    if entry_domains is None:
        return True
    if not entry_domains:
        return True
    return domain in entry_domains

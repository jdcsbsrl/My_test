"""Centralized, environment-scoped access to test secrets.

Secrets are read from the process environment (with the repository-local
dotenv file loaded by the configuration layer).  This module deliberately
does not log or persist secret values.
"""

from __future__ import annotations

import os
from collections.abc import Iterable


def runtime_environment(default: str = "test") -> str:
    """Return the normalized non-production runtime environment."""

    value = os.getenv("TEST_ENV", default).strip().lower()
    return value or default


def get_secret(
    name: str,
    *,
    environment: str | None = None,
    fallbacks: Iterable[str] = (),
) -> str | None:
    """Read a secret using environment-scoped names before fallbacks.

    ``name`` is treated as the canonical suffix.  For example, requesting
    ``USERNAME`` in ``test`` checks ``TEST_USERNAME`` first, then the exact
    name and any explicit fallbacks.  Empty values are treated as missing.
    """

    env = (environment or runtime_environment()).strip().upper()
    candidates: list[str] = []
    if env:
        candidates.append(f"{env}_{name}")
    candidates.append(name)
    candidates.extend(fallbacks)

    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return None

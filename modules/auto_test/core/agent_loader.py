"""Load Agent workspace manifest at process startup (pytest / CLI)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MANIFEST_NAME = "manifest.json"


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _tier_of(entry: dict[str, Any]) -> int:
    t = entry.get("tier")
    if isinstance(t, int):
        return t
    if isinstance(t, str) and t.isdigit():
        return int(t)
    return 2


def _phases_of(entry: dict[str, Any]) -> list[str]:
    p = entry.get("phases")
    if isinstance(p, list):
        return [str(x) for x in p]
    return ["initialization", "coding"]


def _domains_of(entry: dict[str, Any]) -> list[str] | None:
    d = entry.get("domains")
    if isinstance(d, list):
        return [str(x) for x in d]
    return None


def _phase_accepts(phase: str, entry: dict[str, Any]) -> bool:
    phases = _phases_of(entry)
    return phase in phases or "shared" in phases


def _recommend_documents(docs_raw: list[dict[str, Any]], phase: str, domain: str) -> list[str]:
    from modules.auto_test.core.agent_specialization import domain_accepts

    filtered: list[tuple[int, str]] = []
    for entry in docs_raw:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if not isinstance(rel, str):
            continue
        if not _phase_accepts(phase, entry):
            continue
        if not domain_accepts(domain, _domains_of(entry)):
            continue
        filtered.append((_tier_of(entry), rel))
    filtered.sort(key=lambda x: (x[0], x[1]))
    ordered = [p for _, p in filtered]
    # Carlini-style dedup: stable unique order (manifest edits should not duplicate paths)
    return list(dict.fromkeys(ordered))


def bootstrap_agent_workspace(
    root: Path | None = None,
    phase: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    """
    Read `.agents/manifest.json`, validate paths exist, return summary for logging.

    phase: optional explicit phase; if None, uses AGENT_PHASE via agent_phases.resolve_agent_phase().
    domain: optional explicit domain; if None, uses AGENT_DOMAIN via agent_specialization.resolve_agent_domain().
    """
    from modules.auto_test.core.agent_phases import resolve_agent_phase
    from modules.auto_test.core.agent_specialization import resolve_agent_domain

    base = root or repo_root()
    resolved_phase = phase or resolve_agent_phase()
    resolved_domain = domain or resolve_agent_domain()

    manifest_path = base / ".agents" / _MANIFEST_NAME
    if not manifest_path.is_file():
        return {
            "ok": False,
            "error": f"missing {manifest_path.relative_to(base)}",
            "documents": [],
            "phase": resolved_phase,
            "domain": resolved_domain,
            "recommended_documents": [],
            "progress_summary": None,
        }

    with manifest_path.open(encoding="utf-8") as f:
        data = json.load(f)

    docs_raw = data.get("documents", [])
    if not isinstance(docs_raw, list):
        docs_raw = []

    docs: list[dict[str, Any]] = []
    missing: list[str] = []
    for entry in docs_raw:
        if not isinstance(entry, dict):
            continue
        rel = entry.get("path")
        if not isinstance(rel, str):
            continue
        p = (base / rel).resolve()
        exists = p.is_file()
        docs.append(
            {
                "path": rel,
                "exists": exists,
                "tier": _tier_of(entry),
                "phases": _phases_of(entry),
                "domains": _domains_of(entry),
            }
        )
        if not exists:
            missing.append(rel)

    progress_summary = None
    try:
        from modules.auto_test.core.agent_progress import load_progress_json
        from modules.auto_test.core.agent_progress import progress_summary as ps

        pdata = load_progress_json(base)
        if pdata:
            progress_summary = ps(pdata)
    except Exception:  # noqa: BLE001
        progress_summary = None

    recommended = _recommend_documents([e for e in docs_raw if isinstance(e, dict)], resolved_phase, resolved_domain)

    ctx_debug = os.getenv("AGENT_CONTEXT_DEBUG", "").lower() in ("1", "true", "yes")
    context_advisory = None
    if ctx_debug:
        try:
            from modules.auto_test.core.context_budget import ContextBudget

            budget = ContextBudget()
            manifest_text = manifest_path.read_text(encoding="utf-8", errors="replace")
            budget.record("manifest", manifest_text)
            pp = base / ".agents" / "progress.json"
            if pp.is_file():
                budget.record("progress", pp.read_text(encoding="utf-8", errors="replace"))
            context_advisory = budget.advisory_message()
        except Exception:  # noqa: BLE001
            context_advisory = None

    return {
        "ok": len(missing) == 0,
        "manifest_version": data.get("version"),
        "documents": docs,
        "missing": missing,
        "phase": resolved_phase,
        "domain": resolved_domain,
        "recommended_documents": recommended,
        "progress_summary": progress_summary,
        "context_advisory": context_advisory,
    }

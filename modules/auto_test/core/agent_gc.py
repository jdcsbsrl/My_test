"""Garbage collection helpers for generated harness artifacts (reports, logs)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GcPlan:
    """Planned deletion (dry-run friendly)."""

    path: Path
    action: str
    reason: str
    bytes_freed: int | None = None


def _older_than(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def plan_delete_old_files(
    directory: Path,
    *,
    pattern: str,
    max_age_seconds: float,
    now: float | None = None,
) -> list[GcPlan]:
    """Plan deletion of files matching glob pattern older than max_age_seconds."""
    t = now if now is not None else time.time()
    cutoff = t - max_age_seconds
    plans: list[GcPlan] = []
    if not directory.is_dir():
        return plans
    for p in directory.glob(pattern):
        if not p.is_file():
            continue
        if _older_than(p, cutoff):
            try:
                sz = p.stat().st_size
            except OSError:
                sz = None
            plans.append(GcPlan(path=p, action="delete_file", reason=f"older_than {max_age_seconds}s", bytes_freed=sz))
    return plans


def execute_delete_plans(plans: list[GcPlan], *, dry_run: bool) -> tuple[int, int]:
    """Execute delete_file plans. Returns (deleted_count, bytes_freed)."""
    deleted = 0
    freed = 0
    for plan in plans:
        if plan.action != "delete_file":
            continue
        if dry_run:
            if plan.bytes_freed:
                freed += plan.bytes_freed
            continue
        try:
            sz = plan.path.stat().st_size
            plan.path.unlink()
            deleted += 1
            freed += sz
        except OSError:
            continue
    return deleted, freed


def tail_file_in_place(path: Path, *, max_lines: int, backup_suffix: str = ".gc_bak") -> bool:
    """
    If file exceeds max_lines, copy full content to backup then keep last max_lines lines.
    Returns True if rewrite happened.
    """
    if not path.is_file() or max_lines <= 0:
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return False
    backup = path.with_name(path.name + backup_suffix)
    backup.write_text(text, encoding="utf-8")
    path.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    return True

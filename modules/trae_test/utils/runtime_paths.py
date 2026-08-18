"""统一管理项目运行时产物路径。"""

from __future__ import annotations

from pathlib import Path


_PROJECT_MARKERS = ("AGENTS.md", ".git")
RUNTIME_KINDS = frozenset({"cache", "downloads", "logs", "reports", "scripts", "sheet_build", "uploads"})


def project_root(start: str | Path | None = None) -> Path:
    """返回项目根目录。"""
    current = Path(start or __file__).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in _PROJECT_MARKERS):
            return candidate
    raise RuntimeError("无法定位项目根目录")


def runtime_dir(kind: str, *, create: bool = True) -> Path:
    """返回 ``.runtime/<kind>``，并阻止路径越界。"""
    if kind not in RUNTIME_KINDS:
        raise ValueError(f"不支持的运行时目录: {kind}，允许值: {sorted(RUNTIME_KINDS)}")
    root = project_root()
    target = (root / ".runtime" / kind).resolve()
    runtime_root = (root / ".runtime").resolve()
    if target != runtime_root and runtime_root not in target.parents:
        raise ValueError("运行时路径不能离开 .runtime 目录")
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target

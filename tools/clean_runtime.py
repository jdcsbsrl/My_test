"""清理超过保留期限的运行时产物。"""

from __future__ import annotations

import argparse
import fnmatch
import time
from pathlib import Path
from pathlib import PurePosixPath

from modules.trae_test.utils.runtime_paths import RUNTIME_KINDS, project_root


def protected_patterns(root: Path) -> list[str]:
    root = root.resolve()
    patterns: list[str] = []
    keep_files = [root / ".keep"]
    if root.is_dir():
        keep_files.extend(
            keep_file
            for keep_file in root.rglob(".keep")
            if ".runtime" not in keep_file.relative_to(root).parts[:-1]
        )

    for keep_file in sorted(set(keep_files)):
        if not keep_file.is_file() or keep_file.is_symlink():
            continue
        keep_resolved = keep_file.resolve()
        if root != keep_resolved and root not in keep_resolved.parents:
            raise ValueError(f".keep file escapes runtime root: {keep_file}")
        prefix = keep_file.parent.relative_to(root).as_posix()
        for raw_line in keep_file.read_text(encoding="utf-8").splitlines():
            pattern = raw_line.strip()
            if not pattern or pattern.startswith("#"):
                continue
            normalized = pattern.replace("\\", "/")
            pure = PurePosixPath(normalized)
            if pure.is_absolute() or ":" in normalized or ".." in pure.parts:
                raise ValueError(f"Invalid .keep pattern: {pattern!r}")
            normalized = normalized.removeprefix("./")
            patterns.append(f"{prefix}/{normalized}" if prefix != "." else normalized)
    return patterns


def _is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def clean_runtime(keep_days: int = 14, root: Path | None = None, *, dry_run: bool = False) -> list[Path]:
    if keep_days < 0:
        raise ValueError("keep_days 不能为负数")
    project = (root or project_root()).resolve()
    runtime_root = (project / ".runtime").resolve()
    if not _is_within(runtime_root, project):
        raise ValueError(".runtime path escapes the project root")
    cutoff = time.time() - keep_days * 86400
    removed: list[Path] = []
    patterns = protected_patterns(runtime_root)
    for kind in RUNTIME_KINDS:
        directory = runtime_root / kind
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.is_symlink() or path.name == ".keep":
                continue
            if ".runtime" in path.relative_to(runtime_root).parts:
                continue
            resolved = path.resolve()
            if not _is_within(resolved, runtime_root):
                # Never follow or delete a link that resolves outside .runtime.
                continue
            relative = path.relative_to(runtime_root).as_posix()
            if any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                continue
            if path.stat().st_mtime < cutoff:
                removed.append(path)
                if not dry_run:
                    path.unlink()
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期限的 .runtime 产物")
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true", help="只列出待清理文件，不删除")
    args = parser.parse_args()
    removed = clean_runtime(args.keep_days, dry_run=args.dry_run)
    action = "待清理" if args.dry_run else "已清理"
    print(f"{action} {len(removed)} 个运行时文件（保留 {args.keep_days} 天）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

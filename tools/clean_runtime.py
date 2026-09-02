"""清理超过保留期限的运行时产物。"""

from __future__ import annotations

import argparse
import fnmatch
import os
import time
from pathlib import Path
from pathlib import PurePosixPath

from modules.trae_test.utils.runtime_paths import RUNTIME_KINDS, project_root

LEGACY_RUNTIME_ROOT_PATTERNS = (
    "cache-*",
    "pytest-*",
    "test_tmp*",
    "tmp*",
    "node_modules",
    "*_node_modules",
    "check_*.py",
    "verify_*.py",
    "*_debug.log",
)


def protected_patterns(root: Path) -> list[str]:
    root = root.resolve()
    patterns: list[str] = []
    keep_files = [root / ".keep"]
    if root.is_dir():
        for directory, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            dirnames[:] = [name for name in dirnames if not (Path(directory) / name).is_symlink()]
            # Pytest and browser runs may create isolated nested runtime
            # roots. They are independent sandboxes and must not contribute
            # their .keep rules to the project runtime cleaner.
            dirnames[:] = [name for name in dirnames if not (Path(directory) != root and name == ".runtime")]
            if ".keep" in filenames:
                keep_files.append(Path(directory) / ".keep")

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


def _latest_mtime(path: Path) -> float:
    """Return the newest modification time below a legacy root."""
    latest = path.stat().st_mtime
    if path.is_dir() and not path.is_symlink():
        for directory, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
            current = Path(directory)
            dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
            for name in (*dirnames, *filenames):
                candidate = current / name
                try:
                    latest = max(latest, candidate.stat().st_mtime)
                except FileNotFoundError:
                    continue
    return latest


def _legacy_root_matches(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in LEGACY_RUNTIME_ROOT_PATTERNS)


def clean_legacy_roots(runtime_root: Path, cutoff: float, *, dry_run: bool = False) -> list[Path]:
    """Clean recognized legacy roots directly under ``.runtime``."""
    removed: list[Path] = []
    for path in runtime_root.iterdir():
        if not _legacy_root_matches(path) or path.name == ".keep":
            continue
        resolved = path.resolve()
        if not _is_within(resolved, runtime_root) or _latest_mtime(path) >= cutoff:
            continue
        removed.append(path)
        if dry_run:
            continue
        if path.is_dir() and not path.is_symlink():
            import shutil

            shutil.rmtree(path)
        else:
            path.unlink()
    return removed


def clean_runtime(
    keep_days: int = 14,
    root: Path | None = None,
    *,
    dry_run: bool = False,
    clean_legacy: bool = False,
) -> list[Path]:
    if keep_days < 0:
        raise ValueError("keep_days 不能为负数")
    project = (root or project_root()).resolve()
    runtime_root = (project / ".runtime").resolve()
    if not _is_within(runtime_root, project):
        raise ValueError(".runtime path escapes the project root")
    cutoff = time.time() - keep_days * 86400
    removed: list[Path] = []
    patterns = protected_patterns(runtime_root)
    if clean_legacy:
        removed.extend(clean_legacy_roots(runtime_root, cutoff, dry_run=dry_run))
    for kind in sorted(RUNTIME_KINDS):
        directory = runtime_root / kind
        if not directory.is_dir():
            continue
        for directory_name, dirnames, filenames in os.walk(directory, topdown=True, followlinks=False):
            current_dir = Path(directory_name)
            # Do not recurse through symlinked directories. A runtime cleaner
            # must never turn a link into an escape hatch outside .runtime.
            dirnames[:] = [name for name in dirnames if not (current_dir / name).is_symlink()]
            for filename in filenames:
                path = current_dir / filename
                if path.name == ".keep" or path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve()
                if not _is_within(resolved, runtime_root):
                    continue
                relative = path.relative_to(runtime_root).as_posix()
                if any(
                    fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns
                ):
                    continue
                try:
                    is_expired = path.stat().st_mtime < cutoff
                except FileNotFoundError:
                    continue
                if is_expired:
                    removed.append(path)
                    if not dry_run:
                        try:
                            path.unlink()
                        except FileNotFoundError:
                            pass
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期限的 .runtime 产物")
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true", help="只列出待清理文件，不删除")
    parser.add_argument(
        "--clean-legacy-roots",
        action="store_true",
        help="清理 .runtime 根目录下已识别的历史 pytest/tmp/cache 临时目录和脚本",
    )
    args = parser.parse_args()
    removed = clean_runtime(args.keep_days, dry_run=args.dry_run, clean_legacy=args.clean_legacy_roots)
    action = "待清理" if args.dry_run else "已清理"
    print(f"{action} {len(removed)} 个运行时文件（保留 {args.keep_days} 天）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""清理超过保留期限的运行时产物。"""

from __future__ import annotations

import argparse
import fnmatch
import os
import shutil
import time
from pathlib import Path
from pathlib import PurePosixPath

from modules.trae_test.utils.runtime_paths import RUNTIME_KINDS, project_root

LEGACY_RUNTIME_ROOT_PATTERNS = (
    "cache-*",
    "pytest-*",
    "browser-temp-*",
    "validate-report-*",
    "real-response-validation-*",
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


def _record_error(errors: list[str] | None, path: Path, error: OSError) -> None:
    if errors is not None:
        errors.append(f"{path}: {error}")


def _latest_mtime(path: Path, *, errors: list[str] | None = None) -> float | None:
    """Return the newest readable modification time below a legacy root."""
    try:
        latest = path.stat().st_mtime
    except OSError as error:
        _record_error(errors, path, error)
        return None
    if path.is_dir() and not path.is_symlink():

        def on_walk_error(error: OSError) -> None:
            filename = getattr(error, "filename", None)
            _record_error(errors, Path(filename) if filename else path, error)

        for directory, dirnames, filenames in os.walk(
            path,
            topdown=True,
            onerror=on_walk_error,
            followlinks=False,
        ):
            current = Path(directory)
            dirnames[:] = [name for name in dirnames if not (current / name).is_symlink()]
            for name in (*dirnames, *filenames):
                candidate = current / name
                try:
                    latest = max(latest, candidate.stat().st_mtime)
                except OSError as error:
                    _record_error(errors, candidate, error)
                    continue
    return latest


def _legacy_root_matches(path: Path) -> bool:
    return any(fnmatch.fnmatch(path.name, pattern) for pattern in LEGACY_RUNTIME_ROOT_PATTERNS)


def clean_legacy_roots(
    runtime_root: Path,
    cutoff: float,
    *,
    dry_run: bool = False,
    purge: bool = False,
    errors: list[str] | None = None,
) -> list[Path]:
    """Clean recognized legacy roots directly under ``.runtime``.

    By default, the retention cutoff still applies. ``purge=True`` is an
    explicit operator action for removing recent legacy roots as well. Reparse
    points and roots resolving outside ``.runtime`` are always skipped.
    A single inaccessible root must not prevent other roots from being
    inspected and cleaned.
    """
    removed: list[Path] = []
    try:
        candidates = sorted(runtime_root.iterdir(), key=lambda path: path.name.casefold())
    except OSError as error:
        _record_error(errors, runtime_root, error)
        return removed

    for path in candidates:
        if path.name == ".keep" or not _legacy_root_matches(path):
            continue
        try:
            if path.is_symlink():
                continue
            resolved = path.resolve()
            if not _is_within(resolved, runtime_root):
                continue
            if not purge:
                latest_mtime = _latest_mtime(path, errors=errors)
                if latest_mtime is None or latest_mtime >= cutoff:
                    continue
            if dry_run:
                removed.append(path)
                continue
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as error:
            _record_error(errors, path, error)
            continue
        removed.append(path)
    return removed


def clean_runtime(
    keep_days: int = 14,
    root: Path | None = None,
    *,
    dry_run: bool = False,
    clean_legacy: bool = False,
    purge_legacy: bool = False,
    errors: list[str] | None = None,
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
    if clean_legacy or purge_legacy:
        removed.extend(
            clean_legacy_roots(
                runtime_root,
                cutoff,
                dry_run=dry_run,
                purge=purge_legacy,
                errors=errors,
            )
        )
    for kind in sorted(RUNTIME_KINDS):
        directory = runtime_root / kind
        if not directory.is_dir():
            continue

        def on_walk_error(error: OSError) -> None:
            filename = getattr(error, "filename", None)
            _record_error(errors, Path(filename) if filename else directory, error)

        for directory_name, dirnames, filenames in os.walk(
            directory,
            topdown=True,
            onerror=on_walk_error,
            followlinks=False,
        ):
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
                except OSError as error:
                    _record_error(errors, path, error)
                    continue
                if is_expired:
                    if dry_run:
                        removed.append(path)
                        continue
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as error:
                        _record_error(errors, path, error)
                        continue
                    removed.append(path)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期限的 .runtime 产物")
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true", help="只列出待清理路径，不删除")
    legacy_group = parser.add_mutually_exclusive_group()
    legacy_group.add_argument(
        "--clean-legacy-roots",
        action="store_true",
        help="清理 .runtime 根目录下超过保留期的历史临时目录和脚本",
    )
    legacy_group.add_argument(
        "--purge-legacy-roots",
        action="store_true",
        help="显式清理 .runtime 根目录下所有已识别的历史临时目录，不受保留期限制",
    )
    args = parser.parse_args()
    errors: list[str] = []
    removed = clean_runtime(
        args.keep_days,
        dry_run=args.dry_run,
        clean_legacy=args.clean_legacy_roots or args.purge_legacy_roots,
        purge_legacy=args.purge_legacy_roots,
        errors=errors,
    )
    action = "待清理" if args.dry_run else "已清理"
    print(f"{action} {len(removed)} 个运行时路径（保留 {args.keep_days} 天）")
    if args.dry_run:
        for path in removed:
            print(f"  {path}")
    if errors:
        print(f"跳过 {len(errors)} 个无法访问或删除的路径：")
        for error in errors:
            print(f"  {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

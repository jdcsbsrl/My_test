"""清理超过保留期限的运行时产物。"""

from __future__ import annotations

import argparse
import fnmatch
import time
from pathlib import Path

from modules.trae_test.utils.runtime_paths import RUNTIME_KINDS, project_root


def protected_patterns(root: Path) -> list[str]:
    keep_file = root / ".keep"
    if not keep_file.exists():
        return []
    return [line.strip() for line in keep_file.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]


def clean_runtime(keep_days: int = 14, root: Path | None = None) -> list[Path]:
    if keep_days < 0:
        raise ValueError("keep_days 不能为负数")
    runtime_root = (root or project_root()) / ".runtime"
    cutoff = time.time() - keep_days * 86400
    removed: list[Path] = []
    patterns = protected_patterns(runtime_root)
    for kind in RUNTIME_KINDS:
        directory = runtime_root / kind
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file() or path.name == ".keep":
                continue
            relative = path.relative_to(runtime_root).as_posix()
            if any(fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(path.name, pattern) for pattern in patterns):
                continue
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed.append(path)
    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="清理超过保留期限的 .runtime 产物")
    parser.add_argument("--keep-days", type=int, default=14)
    args = parser.parse_args()
    removed = clean_runtime(args.keep_days)
    print(f"已清理 {len(removed)} 个运行时文件（保留 {args.keep_days} 天）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the approved production read-only logistics check without Codex."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.auto_test.core.logistics_tracking_daily import (
    SAMPLE_SIZE,
    TrackingBlockedError,
    ZONE,
    choose_samples,
    load_used_hashes,
    login_session,
    query_strata,
    save_results,
    track_public,
    verdict_counts,
)
from modules.trae_test.utils.runtime_paths import runtime_dir


def _safe_failure(exc: Exception) -> str:
    stage = exc.public_stage if isinstance(exc, TrackingBlockedError) else ""
    detail = f"（{stage}）" if stage else ""
    return f"{type(exc).__name__}{detail}；请检查工作流运行日志和网页访问状态"


def main() -> int:
    parser = argparse.ArgumentParser(description="每日 ERP 与 17TRACK 只读轨迹抽查")
    parser.add_argument(
        "--archive",
        type=Path,
        default=runtime_dir("cache") / "logistics_tracking_archive",
        help="Downloaded history artifact directory",
    )
    parser.add_argument(
        "--export-seed",
        action="store_true",
        help="Write local prior-number hashes to .runtime/cache without network access",
    )
    args = parser.parse_args()
    archive = args.archive.resolve()
    day = datetime.now(ZONE).date()
    if args.export_seed:
        hashes = load_used_hashes(ROOT, archive)
        seed_path = runtime_dir("cache") / f"logistics_tracking_prior_hashes_{day:%Y%m%d}.txt"
        seed_path.write_text(",".join(sorted(hashes)), encoding="ascii")
        print(f"Seed hashes: {len(hashes)}; file: {seed_path}")
        return 0
    values = dotenv_values(ROOT / ".env")
    username = os.environ.get("ERP_PROD_USERNAME") or values.get("ERP_PROD_USERNAME") or ""
    password = os.environ.get("ERP_PROD_PASSWORD") or values.get("ERP_PROD_PASSWORD") or ""
    browser_path = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE") or None
    rows: list[dict[str, str]] = []
    scope: list[str] = []
    try:
        used_hashes = load_used_hashes(ROOT, archive)
    except (OSError, ValueError) as exc:
        print(f"History unavailable: {type(exc).__name__}; no ERP request sent", file=sys.stderr)
        return 2
    try:
        session = login_session(username, password, browser_path=browser_path)
        try:
            candidates, scope = query_strata(session, day)
        finally:
            session.close()
        rows = choose_samples(candidates, used_hashes, day)
        if len(rows) != SAMPLE_SIZE:
            raise RuntimeError("Fewer than ten eligible unique tracking numbers")
        track_public(rows, browser_path=browser_path)
        error = ""
    except Exception as exc:
        # Secrets and authorization headers never enter the report or stdout.
        error = _safe_failure(exc)
    report, sheet = save_results(ROOT, archive, day, rows, scope, used_hashes, error)
    print(f"Report: {report}")
    print(f"Private sheet: {sheet}")
    print(f"Counts: {verdict_counts(rows)}")
    if error:
        print(error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

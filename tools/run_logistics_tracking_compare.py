#!/usr/bin/env python3
"""Collect ERP tracking samples or compare a completed 17TRACK sheet."""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from modules.auto_test.core.logistics_tracking_compare import (
    SAMPLE_SIZE,
    query_candidates,
    read_manual_sheet,
    render_report,
    select_samples,
    write_manual_sheet,
)
from modules.trae_test.utils.runtime_paths import project_root


def main() -> int:
    parser = argparse.ArgumentParser(description="ERP logistics vs public 17TRACK")
    parser.add_argument("mode", choices=("collect", "compare"))
    parser.add_argument("--sheet", type=Path, help="Existing manual CSV sheet for compare mode")
    parser.add_argument("--scope", default="", help="Sampling scope to include in the report")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--logistics-date-begin", help="ERP logisticsDateBeginStr")
    parser.add_argument("--logistics-date-end", help="ERP logisticsDateEndStr")
    parser.add_argument("--status-code", action="append", help="ERP status code; repeat to filter")
    args = parser.parse_args()
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if args.mode == "collect":
        token = os.environ.get("ERP_PROD_TOKEN", "").strip()
        clientid = os.environ.get("ERP_PROD_CLIENTID", "").strip()
        if not token or not clientid:
            parser.error("ERP_PROD_TOKEN and ERP_PROD_CLIENTID are required; no login interface is called")
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "clientid": clientid,
                "Content-Type": "application/json",
            }
        )
        try:
            candidates, truncated = query_candidates(
                session,
                max_pages=args.max_pages,
                logistics_date_begin=args.logistics_date_begin,
                logistics_date_end=args.logistics_date_end,
                tracking_status_list=args.status_code,
            )
        finally:
            session.close()
        selected = select_samples(candidates, day)
        if not selected:
            print("No eligible records; no sheet created", file=sys.stderr)
            return 2
        destination = (
            project_root() / "data" / "private" / f"logistics_tracking_{day:%Y%m%d}_{uuid.uuid4().hex[:8]}.csv"
        )
        write_manual_sheet(destination, selected)
        print(f"Manual 17TRACK sheet: {destination}")
        print(
            f"Eligible scanned: {len(candidates)}; selected: {len(selected)}/{SAMPLE_SIZE}; "
            f"scan truncated: {truncated}"
        )
        return 0 if len(selected) == SAMPLE_SIZE and not truncated else 2

    if args.sheet is None:
        parser.error("--sheet is required in compare mode")
    sheet = args.sheet.resolve(strict=True)
    private_root = (project_root() / "data" / "private").resolve()
    if private_root not in sheet.parents:
        parser.error("--sheet must be under data/private")
    rows = read_manual_sheet(sheet)
    report = render_report(day, rows, scope=args.scope)
    destination = project_root() / "workspace" / f"{day:%Y%m%d}" / f"物流轨迹17TRACK抽查报告_{uuid.uuid4().hex[:8]}.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(report, encoding="utf-8")
    print(f"Report: {destination}")
    return 0 if "结论：**全部一致**" in report else 2


if __name__ == "__main__":
    raise SystemExit(main())

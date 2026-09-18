#!/usr/bin/env python3
"""Periodic, read-only knowledge-base health gate.

The command intentionally reports problems instead of mutating knowledge or
derived indexes.  It is suitable for an external scheduler, but this project
does not create or register a scheduler automatically.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Allow direct execution from the repository root or from another directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.trae_test.utils.runtime_paths import runtime_dir
from tools.kb_manager import KnowledgeBaseManager

EXIT_HEALTHY = 0
EXIT_WARNING = 1
EXIT_BLOCKING = 2


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _status(code: int) -> str:
    return {
        EXIT_HEALTHY: "healthy",
        EXIT_WARNING: "warning",
        EXIT_BLOCKING: "blocking",
    }[code]


def _duplicate_warning(summary: dict[str, Any]) -> list[str]:
    labels = (
        ("normalized_title_duplicate_count", "规范化标题重复"),
        ("cross_file_rule_id_duplicate_count", "跨文件规则 ID 重复"),
        ("exact_content_duplicate_count", "规则正文指纹重复"),
        ("similarity_candidate_count", "规则相似候选"),
    )
    return [
        f"{label}: {summary.get(key, 0)}"
        for key, label in labels
        if isinstance(summary.get(key), int) and summary.get(key, 0) > 0
    ]


def _sanitize_dedupe(value: Any) -> Any:
    """Keep governance metadata while excluding rule bodies from reports."""
    if isinstance(value, dict):
        return {
            key: _sanitize_dedupe(item)
            for key, item in value.items()
            if key not in {"content", "raw_markdown", "business_rules"}
        }
    if isinstance(value, list):
        return [_sanitize_dedupe(item) for item in value]
    return value


def _base_report() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "check_timestamp": _timestamp(),
        "read_only": True,
        "status": "blocking",
        "exit_code": EXIT_BLOCKING,
        "health": None,
        "dedupe": None,
        "errors": [],
        "warnings": [],
        "summary": {},
    }


def build_report(manager: Any, include_dedupe: bool = False) -> dict[str, Any]:
    """Build a machine-readable report without writing project data."""
    report = _base_report()

    try:
        health = manager.health_check()
    except Exception as exc:  # pragma: no cover - covered through main path
        health = {
            "success": False,
            "read_only": True,
            "errors": [{"component": "health_check", "error": str(exc)}],
        }
    report["health"] = health

    health_errors = health.get("errors", []) if isinstance(health, dict) else ["invalid health report"]
    if not isinstance(health, dict) or health.get("read_only") is not True:
        report["errors"].append("health check did not provide a read-only report")
    if not isinstance(health, dict) or not health.get("success", False) or health_errors:
        report["errors"].extend(health_errors or ["health check failed"])

    dedupe = None
    if include_dedupe:
        try:
            dedupe = manager.dedupe_report()
        except Exception as exc:  # pragma: no cover - covered through main path
            dedupe = {
                "success": False,
                "read_only": True,
                "errors": [{"component": "dedupe_report", "error": str(exc)}],
            }
        report["dedupe"] = _sanitize_dedupe(dedupe)
        if not isinstance(dedupe, dict) or dedupe.get("read_only") is not True:
            report["errors"].append("dedupe report did not provide a read-only report")
        if not isinstance(dedupe, dict) or not dedupe.get("success", False):
            dedupe_errors = dedupe.get("unreadable_files", []) if isinstance(dedupe, dict) else []
            report["errors"].extend(dedupe_errors or ["dedupe report failed"])
        elif isinstance(dedupe.get("summary"), dict):
            report["warnings"].extend(_duplicate_warning(dedupe["summary"]))

    scan = health.get("scan", {}) if isinstance(health, dict) else {}
    pending = scan.get("needs_processing", []) if isinstance(scan, dict) else []
    if pending:
        report["warnings"].append(f"待处理知识文件: {len(pending)} 个")

    index_status = health.get("index_status", {}) if isinstance(health, dict) else {}
    if isinstance(index_status, dict):
        for key, label in (("missing_files", "全局索引缺失文件"), ("stale_files", "全局索引过期文件")):
            values = index_status.get(key, [])
            if values:
                report["warnings"].append(f"{label}: {len(values)} 个")

    if report["errors"]:
        report["exit_code"] = EXIT_BLOCKING
    elif report["warnings"]:
        report["exit_code"] = EXIT_WARNING
    else:
        report["exit_code"] = EXIT_HEALTHY
    report["status"] = _status(report["exit_code"])

    summary = report["summary"]
    if isinstance(health, dict):
        summary["registered_file_count"] = health.get("registered_file_count")
        summary["health_error_count"] = len(report["errors"])
    summary["warning_count"] = len(report["warnings"])
    summary["dedupe_checked"] = include_dedupe
    if isinstance(dedupe, dict):
        summary["dedupe_summary"] = dedupe.get("summary", {})
    return report


def write_report(report: dict[str, Any]) -> Path:
    """Write a report under the managed runtime reports directory."""
    report_dir = runtime_dir("reports") / "knowledge_base"
    report_dir.mkdir(parents=True, exist_ok=True)
    filename = f"kb_health_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    report_path = report_dir / filename
    report["report_path"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def run_check(
    manager: Any,
    *,
    include_dedupe: bool = False,
    persist_report: bool = False,
    report_writer: Callable[[dict[str, Any]], Path] = write_report,
) -> tuple[dict[str, Any], int]:
    """Run a health gate and optionally persist its report."""
    report = build_report(manager, include_dedupe=include_dedupe)
    if persist_report:
        try:
            report["report_path"] = str(report_writer(report))
        except Exception as exc:
            report["errors"].append({"component": "report_writer", "error": str(exc)})
            report["exit_code"] = EXIT_BLOCKING
            report["status"] = _status(EXIT_BLOCKING)
            report["summary"]["health_error_count"] = len(report["errors"])
    return report, int(report["exit_code"])


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只读知识库健康门禁")
    parser.add_argument(
        "--include-dedupe",
        action="store_true",
        help="同时执行只读重复候选检查",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="将 JSON 报告写入 .runtime/reports/knowledge_base/",
    )
    return parser


def main(argv: list[str] | None = None, manager_factory: Callable[[], Any] = KnowledgeBaseManager) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        manager = manager_factory()
        report, exit_code = run_check(
            manager,
            include_dedupe=args.include_dedupe,
            persist_report=args.write_report,
        )
    except Exception as exc:
        report = _base_report()
        report["errors"].append({"component": "manager_init", "error": str(exc)})
        report["summary"]["health_error_count"] = 1
        exit_code = EXIT_BLOCKING
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

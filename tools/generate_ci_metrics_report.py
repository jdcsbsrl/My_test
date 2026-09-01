#!/usr/bin/env python3
"""Generate a deterministic Markdown/JSON report for a GitHub Actions run."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CATEGORY_PATTERNS = {
    "超时": re.compile(r"timeout|timed out|超时", re.IGNORECASE),
    "断言失败": re.compile(r"AssertionError|assert\s+", re.IGNORECASE),
    "认证或权限": re.compile(r"\b401\b|\b403\b|unauthori[sz]ed|forbidden|登录失败", re.IGNORECASE),
    "网络或服务": re.compile(r"connection refused|connection reset|ECONN|network|服务不可用", re.IGNORECASE),
    "Playwright": re.compile(r"playwright|browserType|locator|page\.", re.IGNORECASE),
    "依赖或导入": re.compile(r"ModuleNotFoundError|ImportError|No module named|pip install", re.IGNORECASE),
    "测试收集": re.compile(r"collection error|collected 0 items|ERROR collecting", re.IGNORECASE),
}


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def duration_seconds(start: str | None, end: str | None) -> float | None:
    started = parse_time(start)
    completed = parse_time(end)
    if not started or not completed:
        return None
    return max(0.0, (completed - started).total_seconds())


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}小时 {minutes}分 {secs}秒"
    return f"{minutes}分 {secs}秒"


def load_jobs(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [job for job in data.get("jobs", []) if isinstance(job, dict)]


def build_metrics(jobs: list[dict[str, Any]], logs: str, repository: str, run_id: str) -> dict[str, Any]:
    conclusions = Counter(str(job.get("conclusion") or job.get("status") or "unknown") for job in jobs)
    failed_jobs = [job for job in jobs if job.get("conclusion") == "failure"]
    job_rows: list[dict[str, Any]] = []
    durations: list[float] = []

    for job in jobs:
        seconds = duration_seconds(job.get("started_at"), job.get("completed_at"))
        if seconds is not None:
            durations.append(seconds)
        failed_steps = [
            str(step.get("name", "未命名步骤")) for step in job.get("steps", []) if step.get("conclusion") == "failure"
        ]
        job_rows.append(
            {
                "name": str(job.get("name", job.get("id", "未命名 Job"))),
                "status": job.get("status"),
                "conclusion": job.get("conclusion"),
                "duration_seconds": seconds,
                "failed_steps": failed_steps,
            }
        )

    category_counts = {
        category: len(pattern.findall(logs)) for category, pattern in CATEGORY_PATTERNS.items() if pattern.search(logs)
    }
    category_counts = dict(sorted(category_counts.items(), key=lambda item: (-item[1], item[0])))

    start_times = [parse_time(job.get("started_at")) for job in jobs]
    end_times = [parse_time(job.get("completed_at")) for job in jobs]
    valid_starts = [value for value in start_times if value]
    valid_ends = [value for value in end_times if value]
    workflow_seconds = None
    if valid_starts and valid_ends:
        workflow_seconds = max(0.0, (max(valid_ends) - min(valid_starts)).total_seconds())

    return {
        "repository": repository,
        "run_id": run_id,
        "job_count": len(jobs),
        "conclusion_counts": dict(sorted(conclusions.items())),
        "failed_job_count": len(failed_jobs),
        "failed_jobs": [row for row in job_rows if row["conclusion"] == "failure"],
        "workflow_duration_seconds": workflow_seconds,
        "job_duration_average_seconds": sum(durations) / len(durations) if durations else None,
        "job_duration_max_seconds": max(durations) if durations else None,
        "error_category_counts": category_counts,
        "log_character_count": len(logs),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def markdown_report(metrics: dict[str, Any]) -> str:
    counts = metrics["conclusion_counts"]
    lines = [
        "# CI 失败指标报告",
        "",
        f"- 仓库：`{metrics['repository']}`",
        f"- 运行 ID：`{metrics['run_id']}`",
        f"- 生成时间：`{metrics['generated_at']}`",
        "",
        "## 核心指标",
        "",
        f"- Job 总数：**{metrics['job_count']}**",
        f"- 失败 Job：**{metrics['failed_job_count']}**",
        f"- 工作流估算耗时：**{format_duration(metrics['workflow_duration_seconds'])}**",
        f"- Job 平均耗时：**{format_duration(metrics['job_duration_average_seconds'])}**",
        f"- 最长 Job 耗时：**{format_duration(metrics['job_duration_max_seconds'])}**",
        f"- 纳入统计的日志字符数：**{metrics['log_character_count']}**",
        "",
        "## Job 结果分布",
        "",
        "| 结果 | 数量 |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in counts.items())
    lines.extend(["", "## 失败 Job", ""])
    if metrics["failed_jobs"]:
        lines.extend(["| Job | 耗时 | 失败步骤 |", "|---|---:|---|"])
        for job in metrics["failed_jobs"]:
            steps = "、".join(job["failed_steps"]) or "未识别"
            lines.append(f"| {job['name']} | {format_duration(job['duration_seconds'])} | {steps} |")
    else:
        lines.append("未识别到失败 Job。")

    lines.extend(["", "## 日志错误类型统计", ""])
    if metrics["error_category_counts"]:
        lines.extend(["| 类型 | 匹配次数 |", "|---|---:|"])
        lines.extend(f"| {key} | {value} |" for key, value in metrics["error_category_counts"].items())
    else:
        lines.append("未匹配到预设错误类型；请查看 `failed-jobs.log`。")

    lines.extend(
        [
            "",
            "## 使用建议",
            "",
            "- 优先查看失败 Job 和失败步骤，再结合 `failed-jobs.log` 定位具体错误。",
            "- 多次运行时比较失败 Job 数量、工作流耗时和错误类型，可判断稳定性趋势。",
            "- 本报告基于规则统计，不使用外部 AI，不替代人工判断。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True)
    parser.add_argument("--logs", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--json", dest="json_path", type=Path, required=True)
    args = parser.parse_args()

    jobs = load_jobs(args.jobs)
    logs = args.logs.read_text(encoding="utf-8", errors="replace") if args.logs.exists() else ""
    metrics = build_metrics(jobs, logs, args.repository, args.run_id)
    markdown = markdown_report(metrics)
    args.markdown.write_text(markdown, encoding="utf-8")
    args.json_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Deprecated compatibility entry point for the retired multi-agent CLI.

The former script owned a second test-case generation workflow and depended
on deleted template files.  Keep this small shim for external callers that
still invoke the historical path: code review and environment checks forward
to the current AuditAgent API, while generation and interactive mode return a
clear migration message instead of silently using stale behavior.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="旧多 Agent 入口兼容层（已弃用）",
        epilog=(
            "测试用例生成请使用 python tools/case_generator_cli.py generate --help；"
            "回归测试请使用 python tools/run_regression.py --help。"
        ),
    )
    parser.add_argument(
        "--task",
        choices=("test_case", "code_review", "environment_check", "full_audit", "interactive"),
    )
    parser.add_argument("--requirement-id", help="仅保留旧参数以兼容脚本调用")
    parser.add_argument("--requirement-name", help="仅保留旧参数以兼容脚本调用")
    parser.add_argument("--file", help="代码审核目标文件")
    parser.add_argument("--env", default=os.getenv("TEST_ENV", "test"), help="环境检查目标环境")
    parser.add_argument("--interactive", action="store_true", help="旧交互模式（已停用）")
    return parser


def _migration_message(task: str) -> str:
    if task == "test_case":
        return (
            "旧测试用例生成工作流已停用，旧模板已删除；请使用 "
            "python tools/case_generator_cli.py generate --help 提供需求正文。"
        )
    return "旧多 Agent 交互/全能审核入口已停用；请使用当前 CLI 和 AuditAgent API。"


def _run_code_review(file_path: str) -> int:
    from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent

    target = Path(file_path).resolve()
    if not target.is_file():
        print(f"代码文件不存在: {file_path}", file=sys.stderr)
        return 2
    result = AuditAgent().audit_code(str(target))
    print(
        f"代码审核: {'通过' if result.passed else '未通过'} "
        f"(errors={len(result.errors)}, warnings={len(result.warnings)})"
    )
    return 0 if result.passed else 1


def _run_environment_check(env_name: str) -> int:
    from modules.auto_test.core.config_manager import get_config
    from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent

    config = get_config(env_name)
    result = AuditAgent().audit_environment(config.config)
    print(
        f"环境审核 [{config.env}]: {'通过' if result.passed else '未通过'} "
        f"(errors={len(result.errors)}, warnings={len(result.warnings)})"
    )
    return 0 if result.passed else 1


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    task = "interactive" if args.interactive or not args.task else args.task

    if task == "code_review":
        if not args.file:
            print("请提供 --file 参数", file=sys.stderr)
            return 2
        return _run_code_review(args.file)
    if task == "environment_check":
        return _run_environment_check(args.env)

    print(_migration_message(task), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

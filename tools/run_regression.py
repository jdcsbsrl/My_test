#!/usr/bin/env python3
"""
运行回归测试并生成可视化报告
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.report_generator import run_regression_tests


def main() -> int:
    parser = argparse.ArgumentParser(description="运行 TEST 环境回归测试并生成报告")
    parser.add_argument("--env", choices=("test", "uat"), default="test")
    parser.add_argument("--scope", choices=("smoke", "module", "release"), default="module")
    parser.add_argument("--case-id", action="append", help="登记表中的活动用例ID，可重复")
    parser.add_argument("--requirement-id", help="按需求ID计算规则影响范围")
    parser.add_argument("--impact-query", help="通过KnowledgeRetriever检索完整规则并选择受影响用例")
    parser.add_argument("--execute", action="store_true", help="执行已登记用例；默认只预览选择")
    args = parser.parse_args()
    if args.case_id or args.impact_query:
        from modules.trae_test.utils.case_registry import CaseRegistry
        from modules.auto_test.core.registered_regression import plan_registered_cases, run_registered_cases

        registry = CaseRegistry()
        selected_ids = args.case_id or []
        if args.impact_query:
            if not args.requirement_id:
                parser.error("--impact-query requires --requirement-id")
            from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
            from modules.trae_test.utils.rule_contracts import impact_plan

            impact = impact_plan(
                registry,
                KnowledgeRetriever().retrieve(args.impact_query, mode="hybrid"),
                args.requirement_id,
            )
            selected_ids.extend(impact["selected_case_ids"])
            print(json.dumps(impact, ensure_ascii=False, indent=2))
        if not selected_ids:
            print("没有受影响的活动用例")
            return 0
        selected = plan_registered_cases(registry, selected_ids)
        for row in selected:
            print(row["case_id"], f"v{row['version']}", row["script_id"])
        return run_registered_cases(registry, selected, args.env) if args.execute else 0
    report = run_regression_tests(env_name=args.env, scope=args.scope)
    return (
        1 if report.release_decision["status"] == "BLOCKED" else 2 if not report.release_decision["can_deliver"] else 0
    )


if __name__ == "__main__":
    sys.exit(main())

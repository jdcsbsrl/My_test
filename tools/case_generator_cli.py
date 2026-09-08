#!/usr/bin/env python3
"""Generate from requirement text and manage current cases without changing Excel fields."""

import argparse
import json
import sys
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def list_templates():
    from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

    for name in KnowledgeRetriever().list_available_files():
        if "模板" in name or "测试用例" in name:
            print(name)


def generate_case(
    module_name,
    func_name,
    priority="P1",
    requirement_id=None,
    *,
    requirement=None,
    provider="local-rule",
    register=False,
    candidate=None,
    user_evidence=None,
):
    from modules.trae_test.utils.case_generation_service import CaseGenerationService
    from modules.trae_test.utils.case_registry import CaseRegistry
    from modules.trae_test.utils.excel_generator import ExcelGenerator
    from modules.trae_test.utils.runtime_paths import runtime_dir

    if register and not requirement_id:
        raise ValueError("登记用例必须提供稳定的需求ID")
    if not requirement:
        raise ValueError("请通过 --requirement 或 --requirement-file 提供需求正文")
    service = CaseGenerationService()
    result = service.generate(
        requirement,
        requirement_id or "",
        provider=provider,
        priority=priority,
        candidate=candidate,
        user_evidence=user_evidence,
    )
    registry = CaseRegistry() if register else None
    if registry:
        result["changes"] = registry.propose(result["cases"], requirement_id)
    report = runtime_dir("reports") / f"case_generation_{uuid.uuid4().hex}.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"生成诊断: {report}")
    if result.get("semantic_status") == "unverified":
        print("业务语义未验证：当前仅完成已实现的结构审核，请核对业务依据。")
    if result["status"] != "ready":
        if result["status"] == "generation_failed":
            print("生成内容未通过自动校验；这是生成问题，无需确认固定字段。详情见生成诊断。")
        for question in result["questions"]:
            print(question)
        return 2
    decision = result.get("release_decision", {})
    if not decision.get("can_deliver", False):
        print("发布门禁未通过：请查看生成诊断中的阻断项或待确认项。")
        for issue in decision.get("blocking_issues", []) + decision.get("required_review", []):
            print(issue.get("message", issue), file=sys.stderr)
        return 2
    if registry and any(item["action"] == "review_update" for item in result["changes"]):
        print("存在同名用例变更，请使用 update 指定用例ID和变更原因；未激活新版本。")
        return 2
    from modules.trae_test.utils.workspace_manager import workspace_manager

    output_path = Path(
        workspace_manager.generate_file_path(
            requirement_name=f"{module_name}_{func_name}", requirement_id=requirement_id
        )
    )
    if output_path.exists():
        output_path = output_path.with_stem(f"{output_path.stem}_{uuid.uuid4().hex[:10]}")
    output = ExcelGenerator.generate_excel(
        result["cases"],
        requirement_name=f"{module_name}_{func_name}",
        requirement_id=requirement_id,
        output_path=str(output_path),
    )
    service.gateway.audit(output, "all", {"block_on_fail": True})
    print(f"测试用例: {output}")
    if registry:
        for case in result["cases"]:
            case_id, version = registry.save(case, requirement_id)
            print(f"已登记: {case_id} v{version}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="需求生成与用例版本管理")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list-templates")
    gen = commands.add_parser("generate")
    gen.add_argument("--module", "-m", required=True)
    gen.add_argument("--function", "-f", required=True)
    gen.add_argument("--priority", "-p", choices=("P0", "P1", "P2"), default="P1")
    gen.add_argument("--requirement-id", "-r")
    content = gen.add_mutually_exclusive_group(required=True)
    content.add_argument("--requirement")
    content.add_argument("--requirement-file", type=Path)
    gen.add_argument("--provider", choices=("local-rule", "self-hosted-llm"), default="local-rule")
    gen.add_argument("--register", action="store_true")
    gen.add_argument("--candidate-file", type=Path, help="本地Agent依据知识生成的候选JSON，仍经过固定字段及完整审核")
    evidence = gen.add_mutually_exclusive_group()
    evidence.add_argument("--user-evidence", help="用户明确提供的业务依据；会与知识库来源分开记录")
    evidence.add_argument("--user-evidence-file", type=Path, help="包含用户明确业务依据的本地文本文件")
    listing = commands.add_parser("list-cases")
    listing.add_argument("--requirement-id")
    listing.add_argument("--history", action="store_true")
    health = commands.add_parser("health", help="检查未执行、失败、失效脚本和相似用例，不自动停用")
    health.add_argument("--requirement-id")
    health.add_argument("--stale-days", type=int, default=30)
    impact = commands.add_parser("impact", help="通过检索API比较规则版本，预览受影响用例及相关P0")
    impact.add_argument("--requirement-id", required=True)
    impact.add_argument("--query", required=True, help="检索该需求的完整相关规则")
    retire = commands.add_parser("retire")
    retire.add_argument("case_id")
    retire.add_argument("--reason", required=True)
    update = commands.add_parser("update")
    update.add_argument("case_id")
    update.add_argument("--report", type=Path, required=True)
    update.add_argument("--index", type=int, default=0)
    update.add_argument("--reason", required=True)
    update.add_argument("--script-id", default="")
    args = parser.parse_args()
    try:
        if args.command == "list-templates":
            list_templates()
            return 0
        if args.command == "generate":
            requirement = (
                args.requirement_file.read_text(encoding="utf-8") if args.requirement_file else args.requirement
            )
            user_evidence = (
                args.user_evidence_file.read_text(encoding="utf-8") if args.user_evidence_file else args.user_evidence
            )
            return generate_case(
                args.module,
                args.function,
                args.priority,
                args.requirement_id,
                requirement=requirement,
                provider=args.provider,
                register=args.register,
                candidate=json.loads(args.candidate_file.read_text(encoding="utf-8")) if args.candidate_file else None,
                user_evidence=user_evidence,
            )
        from modules.trae_test.utils.case_registry import CaseRegistry

        registry = CaseRegistry()
        if args.command == "impact":
            from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever
            from modules.trae_test.utils.rule_contracts import impact_plan

            sources = KnowledgeRetriever().retrieve(args.query, mode="hybrid")
            print(json.dumps(impact_plan(registry, sources, args.requirement_id), ensure_ascii=False, indent=2))
        elif args.command == "health":
            from modules.trae_test.utils.case_health import case_health

            print(
                json.dumps(
                    case_health(registry, args.requirement_id, stale_days=args.stale_days), ensure_ascii=False, indent=2
                )
            )
        elif args.command == "list-cases":
            for row in registry.list_cases(args.requirement_id, active_only=not args.history):
                print(
                    row["case_id"],
                    row["version"],
                    row["active"],
                    row["content"]["用例名称"],
                    row["last_status"] or "未执行",
                )
        elif args.command == "retire":
            registry.retire(args.case_id, args.reason)
        elif args.command == "update":
            if args.script_id:
                from modules.auto_test.core.registered_regression import validate_script_node

                validate_script_node(args.script_id)
            from modules.trae_test.orchestrator.audit_gateway import AuditGateway
            from modules.trae_test.utils.runtime_quality import read_runtime_quality, attach_runtime_quality
            from modules.trae_test.utils.template_builder import LEGACY_RUNTIME_FIELDS

            case = json.loads(args.report.read_text(encoding="utf-8"))["cases"][args.index]
            context = {"block_on_fail": True}
            if case.get("_runtime_rule_binding"):
                from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever

                context["knowledge_sources"] = KnowledgeRetriever().retrieve(case["用例名称"], mode="hybrid")
            result = AuditGateway().audit([case], "test_case", context)
            quality = read_runtime_quality(case)
            quality.final_audit_passed = result.passed
            quality.needs_human_review = False
            attach_runtime_quality(case, quality)
            for key in LEGACY_RUNTIME_FIELDS:
                case.pop(key, None)
            print(
                registry.save(case, case["需求ID"], case_id=args.case_id, script_id=args.script_id, reason=args.reason)
            )
        return 0
    except Exception as exc:
        print(f"操作失败: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

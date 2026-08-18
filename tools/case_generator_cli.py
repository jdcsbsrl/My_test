#!/usr/bin/env python3
"""
测试用例生成命令行工具
集成 trae_test 的测试用例生成功能 + 审核Agent
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from modules.trae_test.orchestrator import AgentOrchestrator, AuditConfig, OrchestratorConfig, WorkflowConfig
from modules.trae_test.utils.knowledge_retriever import KnowledgeRetriever


def list_templates():
    """列出可用模板"""
    print("=" * 60)
    print("可用测试用例模板")
    print("=" * 60)

    kb = KnowledgeRetriever()
    templates = [
        name
        for name in kb.list_available_files()
        if "模板" in name or "test_case" in name.lower() or "测试用例" in name
    ]

    if templates:
        print(f"\n找到 {len(templates)} 个模板:\n")
        for template in templates:
            print(f"  - {template}")
    else:
        print("\n未找到模板文件，请确保知识库目录正确")

    print()


def create_orchestrator():
    """创建配置好的编排器"""
    config = OrchestratorConfig(
        audit_config=AuditConfig(
            enforce_hard_block=True, enabled=True, strict_level=3, detailed_logging=True, auto_select_audit_types=True
        ),
        workflow_config=WorkflowConfig(
            name="测试用例生成", enable_parallel=False, record_execution_time=True, generate_report=True
        ),
        debug_mode=False,
        notify_callback=print,
    )
    return AgentOrchestrator(config)


def generate_case(module_name: str, func_name: str, priority: str, requirement_id: str = None):
    """生成测试用例 - 集成审核Agent"""
    print("\n" + "=" * 80)
    print("📋 测试用例生成 + 实时审核")
    print("=" * 80)
    print(f"  模块: {module_name}")
    print(f"  功能: {func_name}")
    print(f"  优先级: {priority}")
    if requirement_id:
        print(f"  需求ID: {requirement_id}")
    print()

    # 1. 首先从知识库获取或生成测试用例
    try:
        # 先尝试从知识库获取模板，没有的话用默认模板
        kb = KnowledgeRetriever()
        template_cases = kb.get_template_cases(module_name, func_name)
    except Exception:
        # 如果知识库获取失败，使用默认模板
        template_cases = []

    # 2. 如果没有模板，创建默认测试用例
    if not template_cases:
        print("⚠️  未找到匹配的模板，使用默认测试用例")
        template_cases = create_default_test_cases(module_name, func_name, priority, requirement_id)

    # 3. 使用Agent编排器执行完整流程（包含审核）
    orchestrator = create_orchestrator()

    requirement_name = f"{module_name}_{func_name}"

    try:
        result = orchestrator.execute_test_case_generation(
            requirement_id=requirement_id or "REQ_DEFAULT", requirement_name=requirement_name, test_cases=template_cases
        )

        print("\n" + "=" * 80)
        print("✅ 测试用例生成完成！")
        print("=" * 80)

        if result:
            print(f"📄 输出文件: {result}")

        # 生成并保存报告
        from datetime import datetime
        from modules.trae_test.utils.runtime_paths import runtime_dir

        report_path = str(
            runtime_dir("reports")
            / f"测试用例生成报告_{requirement_id or 'DEFAULT'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )

        # 获取最后执行的工作流
        workflows = list(orchestrator.workflow_manager.workflows.values())
        if workflows:
            from modules.trae_test.orchestrator import WorkflowReporter

            reporter = WorkflowReporter(orchestrator.monitor)
            reporter.save_report(workflows[-1], report_path, include_logs=True)
            print(f"📊 报告已保存: {report_path}")

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 测试用例生成失败！")
        print("=" * 80)
        print(f"错误: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


def create_default_test_cases(module_name: str, func_name: str, priority: str, requirement_id: str):
    """创建默认测试用例"""
    from modules.trae_test.utils.test_case_generator import DEFAULT_CREATOR, TestCaseGenerator

    generator = TestCaseGenerator()

    # 根据优先级确定用例等级
    level_map = {"P0": "高", "P1": "高", "P2": "中"}
    level = level_map.get(priority, "高")

    # 基础用例 - 正常流程
    generator.create_case(
        directory=f"{module_name} - {func_name} - 正常流程",
        name=f"{func_name}_正常流程_功能验证",
        requirement_id=requirement_id or "",
        precondition="系统正常运行，用户已登录",
        steps="1. 进入功能页面\n2. 执行主要操作\n3. 提交数据",
        expected_result="1. 页面正常加载\n2. 操作执行成功\n3. 数据保存成功",
        case_type="功能测试",
        case_status="正常",
        level=level,
        creator=DEFAULT_CREATOR,
        is_automation="否",
        related_defect_id="",
        knowledge_link="",
    )

    # 边界测试
    generator.create_case(
        directory=f"{module_name} - {func_name} - 边界测试",
        name=f"{func_name}_边界条件_最小值测试",
        requirement_id=requirement_id or "",
        precondition="系统正常运行，用户已登录",
        steps="1. 输入最小允许值\n2. 执行操作",
        expected_result="1. 系统正常处理\n2. 无报错",
        case_type="边界测试",
        case_status="正常",
        level=level,
        creator=DEFAULT_CREATOR,
        is_automation="否",
        related_defect_id="",
        knowledge_link="",
    )

    # 异常测试
    generator.create_case(
        directory=f"{module_name} - {func_name} - 异常测试",
        name=f"{func_name}_异常情况_空值输入",
        requirement_id=requirement_id or "",
        precondition="系统正常运行，用户已登录",
        steps="1. 留空必填字段\n2. 尝试提交",
        expected_result="1. 系统提示必填项\n2. 不允许提交",
        case_type="异常测试",
        case_status="正常",
        level=level,
        creator=DEFAULT_CREATOR,
        is_automation="否",
        related_defect_id="",
        knowledge_link="",
    )

    return generator.cases


def main():
    parser = argparse.ArgumentParser(description="test_erp 测试用例生成工具 (带实时审核)")
    subparsers = parser.add_subparsers(title="命令", dest="command")

    # list 命令
    list_parser = subparsers.add_parser("list-templates", help="列出可用模板")

    # generate 命令
    gen_parser = subparsers.add_parser("generate", help="生成测试用例 (包含实时审核)")
    gen_parser.add_argument("--module", "-m", required=True, help="模块名称")
    gen_parser.add_argument("--function", "-f", required=True, help="功能名称")
    gen_parser.add_argument("--priority", "-p", default="P1", help="优先级 (P0, P1, P2)")
    gen_parser.add_argument("--requirement-id", "-r", help="需求ID (可选)")

    args = parser.parse_args()

    if args.command == "list-templates":
        list_templates()
        return 0
    elif args.command == "generate":
        return generate_case(
            module_name=args.module, func_name=args.function, priority=args.priority, requirement_id=args.requirement_id
        )
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())

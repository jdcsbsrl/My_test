"""多Agent协同工作系统 - 统一入口

使用方法：
1. 测试用例生成：
   python multi_agent_runner.py --task test_case --requirement-id 1001345 --requirement-name "客户报价明细导出优化"

2. 代码审核：
   python multi_agent_runner.py --task code_review --file path/to/file.py

3. 环境检查：
   python multi_agent_runner.py --task environment_check

4. 交互模式：
   python multi_agent_runner.py --interactive
"""

import argparse
import os
import sys

# 添加项目路径
project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from modules.trae_test.orchestrator import (
    AgentOrchestrator,
    AuditConfig,
    AuditType,
    OrchestratorConfig,
    OutputMode,
    RetryConfig,
    WorkflowConfig,
    WorkflowReporter,
)


def print_banner():
    """打印横幅"""
    banner = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                    多Agent协同工作系统 v2.0                                   ║
║                    Multi-Agent Collaboration System                          ║
║                                                                              ║
║  功能：                                                                     ║
║  1. 测试用例生成 - 自动生成符合规范的测试用例                                  ║
║  2. 代码审核 - 全能审核（规范、安全、环境、影响）                              ║
║  3. 环境检查 - 验证执行环境配置                                               ║
║  4. 全能审核 - 全方位质量监督                                                 ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """
    print(banner)


def create_orchestrator() -> AgentOrchestrator:
    """创建编排器"""
    config = OrchestratorConfig(
        audit_config=AuditConfig(
            enforce_hard_block=True,
            enabled=True,
            strict_level=3,
            detailed_logging=True,
            timeout=30,
            auto_select_audit_types=True,
        ),
        retry_config=RetryConfig(max_retries=3, base_delay=1.0, exponential_backoff=True, enabled=True),
        workflow_config=WorkflowConfig(
            name="multi_agent_workflow",
            enable_parallel=False,
            max_parallel_tasks=3,
            record_execution_time=True,
            generate_report=True,
        ),
        output_mode=OutputMode.BOTH,
        debug_mode=False,
        notify_callback=print,
    )

    return AgentOrchestrator(config)


def run_test_case_generation(orchestrator: AgentOrchestrator, requirement_id: str, requirement_name: str):
    """运行测试用例生成"""
    print("\n" + "=" * 80)
    print("📋 开始生成测试用例")
    print(f"需求ID: {requirement_id}")
    print(f"需求名称: {requirement_name}")
    print("=" * 80 + "\n")

    # 从模板文件加载测试用例
    template_path = os.path.join(project_dir, "data", "test_case_templates", "batch_modify_sku.json")
    if not os.path.exists(template_path):
        print(f"❌ 测试用例模板文件不存在: {template_path}")
        return

    import json

    with open(template_path, encoding="utf-8") as f:
        template_content = f.read()

    # 替换模板中的占位符
    template_content = template_content.replace("{requirement_id}", requirement_id)
    test_cases = json.loads(template_content)

    try:
        # 执行工作流
        result = orchestrator.execute_test_case_generation(
            requirement_id=requirement_id, requirement_name=requirement_name, test_cases=test_cases
        )

        print("\n" + "=" * 80)
        print("✅ 测试用例生成完成！")
        print("=" * 80)

        if result:
            print(f"输出文件: {result}")

        # 获取最后执行的工作流并显示详细信息
        workflows = list(orchestrator.workflow_manager.workflows.values())
        if workflows:
            last_workflow = workflows[-1]

            # 打印工作流详细信息和审核结果
            print("\n" + "-" * 80)
            print("📊 工作流详情")
            print("-" * 80)

            for step in last_workflow.steps:
                print(f"\n📍 步骤: {step.name}")
                print(f"   状态: {step.status.value}")

                if step.audit_result:
                    print(f"   📋 审核结果: {'✅ 通过' if step.audit_result.passed else '❌ 未通过'}")
                    if step.audit_result.errors:
                        print(f"   ❌ 错误 ({len(step.audit_result.errors)}):")
                        for error in step.audit_result.errors:
                            print(f"      - [{error['code']}] {error['message']}")
                            if error.get("location"):
                                print(f"        位置: {error['location']}")
                    if step.audit_result.warnings:
                        print(f"   ⚠️ 警告 ({len(step.audit_result.warnings)}):")
                        for warning in step.audit_result.warnings:
                            print(f"      - [{warning['code']}] {warning['message']}")
                            if warning.get("location"):
                                print(f"        位置: {warning['location']}")
                    if step.audit_result.suggestions:
                        print(f"   💡 建议 ({len(step.audit_result.suggestions)}):")
                        for suggestion in step.audit_result.suggestions:
                            print(f"      - {suggestion}")
                    print(f"   ⏱️ 执行时间: {step.audit_result.execution_time:.2f}秒")

                if step.end_time and step.start_time:
                    print(f"   ⏱️ 总耗时: {(step.end_time - step.start_time).total_seconds():.2f}秒")

        # 生成报告
        reporter = WorkflowReporter(orchestrator.monitor)
        report_path = os.path.join(project_dir, "workspace", "test_erp", f"测试用例生成报告_{requirement_id}.txt")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        if workflows:
            last_workflow = workflows[-1]
            reporter.save_report(last_workflow, report_path, include_logs=True)
            print(f"\n📄 报告已保存: {report_path}")

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 测试用例生成失败！")
        print("=" * 80)
        print(f"错误: {str(e)}")
        import traceback

        traceback.print_exc()


def run_code_review(orchestrator: AgentOrchestrator, file_path: str):
    """运行代码审核"""
    print("\n" + "=" * 80)
    print("🔍 开始代码审核")
    print(f"文件路径: {file_path}")
    print("=" * 80 + "\n")

    if not os.path.exists(file_path):
        print(f"❌ 文件不存在: {file_path}")
        return

    try:
        # 读取文件内容
        try:
            with open(file_path, encoding="utf-8") as f:
                code_content = f.read()
        except FileNotFoundError:
            print(f"❌ 文件不存在: {file_path}")
            return
        except UnicodeDecodeError:
            print(f"❌ 文件编码不支持: {file_path}，请确保文件为 UTF-8 编码")
            return

        # 执行代码审核工作流
        result = orchestrator.execute_code_review(code=code_content, language="python")

        print("\n" + "=" * 80)
        print("🔍 代码审核完成")
        print("=" * 80)

        print(f"\n审核结果: {'✅ 通过' if result.passed else '❌ 未通过'}")
        print(f"错误数量: {len(result.errors)}")
        print(f"警告数量: {len(result.warnings)}")

        if result.errors:
            print("\n错误详情:")
            for i, error in enumerate(result.errors, 1):
                print(f"  {i}. [{error['code']}] {error['message']}")
                if error.get("location"):
                    print(f"     位置: {error['location']}")

        if result.warnings:
            print("\n警告详情:")
            for i, warning in enumerate(result.warnings, 1):
                print(f"  {i}. [{warning['code']}] {warning['message']}")

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 代码审核失败！")
        print("=" * 80)
        print(f"错误: {str(e)}")
        import traceback

        traceback.print_exc()


def run_environment_check(orchestrator: AgentOrchestrator):
    """运行环境检查"""
    print("\n" + "=" * 80)
    print("🔍 开始环境检查")
    print("=" * 80 + "\n")

    # 检查环境配置
    env_config = {
        "python_version": "3.14.4",
        "dependencies": ["pytest", "playwright", "requests", "openpyxl", "pyyaml", "python-dotenv"],
        "env_vars": {"ENVIRONMENT": "test", "DEBUG": "false"},
    }

    try:
        # 执行环境审核
        from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent

        audit_agent = AuditAgent()

        result = audit_agent.audit(target=env_config, audit_type=AuditType.ENVIRONMENT)

        print("\n" + "=" * 80)
        print("🔍 环境检查完成")
        print("=" * 80)

        print(f"\n审核结果: {'✅ 通过' if result.passed else '❌ 未通过'}")
        print(f"错误数量: {len(result.errors)}")
        print(f"警告数量: {len(result.warnings)}")

        if result.errors:
            print("\n错误详情:")
            for i, error in enumerate(result.errors, 1):
                print(f"  {i}. [{error['code']}] {error['message']}")

        if result.warnings:
            print("\n警告详情:")
            for i, warning in enumerate(result.warnings, 1):
                print(f"  {i}. [{warning['code']}] {warning['message']}")

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 环境检查失败！")
        print("=" * 80)
        print(f"错误: {str(e)}")
        import traceback

        traceback.print_exc()


def run_full_audit(orchestrator: AgentOrchestrator):
    """运行全能审核"""
    print("\n" + "=" * 80)
    print("🔍 开始全能审核")
    print("=" * 80 + "\n")

    try:
        from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent

        audit_agent = AuditAgent()

        # 测试用例审核
        test_cases = [
            {
                "用例目录": "测试模块",
                "用例名称": "测试用例1",
                "需求ID": "1001",
                "前置条件": "登录系统",
                "用例步骤": "1. 执行操作",
                "预期结果": "操作成功",
                "用例类型": "功能测试",
                "用例状态": "草稿",
                "用例等级": "高",
                "创建人": "测试",
                "优先级": "P1",
                "是否可自动化": "否",
                "关联缺陷ID": "",
                "回归测试标识": "否",
                "知识库关联": "",
            }
        ]

        print("1️⃣ 测试用例审核...")
        result1 = audit_agent.audit(test_cases, AuditType.TEST_CASE)
        print(f"   结果: {'✅ 通过' if result1.passed else '❌ 未通过'}")

        print("2️⃣ 代码规范审核...")
        code_sample = "def hello():\n    print('Hello World')"
        result2 = audit_agent.audit(code_sample, AuditType.CODE)
        print(f"   结果: {'✅ 通过' if result2.passed else '❌ 未通过'}")

        print("3️⃣ 环境审核...")
        env_config = {"python_version": "3.14", "dependencies": ["pytest"]}
        result3 = audit_agent.audit(env_config, AuditType.ENVIRONMENT)
        print(f"   结果: {'✅ 通过' if result3.passed else '❌ 未通过'}")

        print("4️⃣ 安全审核...")
        code_with_password = "password = 'secret123'"
        result4 = audit_agent.audit(code_with_password, AuditType.SECURITY)
        print(f"   结果: {'✅ 通过' if result4.passed else '❌ 未通过'}")

        print("\n" + "=" * 80)
        print("🔍 全能审核完成")
        print("=" * 80)

        print("\n总结:")
        print(f"  测试用例审核: {'✅ 通过' if result1.passed else '❌ 未通过'}")
        print(f"  代码规范审核: {'✅ 通过' if result2.passed else '❌ 未通过'}")
        print(f"  环境审核: {'✅ 通过' if result3.passed else '❌ 未通过'}")
        print(f"  安全审核: {'✅ 通过' if result4.passed else '❌ 未通过'}")

    except Exception as e:
        print("\n" + "=" * 80)
        print("❌ 全能审核失败！")
        print("=" * 80)
        print(f"错误: {str(e)}")
        import traceback

        traceback.print_exc()


def safe_input(prompt: str, required: bool = True) -> str:
    """带验证的用户输入，空值时重新提示。"""
    while True:
        value = input(prompt).strip()
        if value or not required:
            return value
        print("输入不能为空，请重新输入")


def interactive_mode():
    """交互模式"""
    print("\n" + "=" * 80)
    print("欢迎使用多Agent协同工作系统！")
    print("=" * 80)
    print("\n可用命令:")
    print("  1. test - 测试用例生成")
    print("  2. code - 代码审核")
    print("  3. env - 环境检查")
    print("  4. audit - 全能审核")
    print("  5. help - 显示帮助")
    print("  6. exit - 退出")
    print()

    orchestrator = create_orchestrator()

    while True:
        try:
            cmd = safe_input("\n请输入命令: ").lower()

            if cmd == "1" or cmd == "test":
                req_id = safe_input("请输入需求ID: ")
                req_name = safe_input("请输入需求名称: ")
                run_test_case_generation(orchestrator, req_id, req_name)

            elif cmd == "2" or cmd == "code":
                file_path = safe_input("请输入文件路径: ")
                run_code_review(orchestrator, file_path)

            elif cmd == "3" or cmd == "env":
                run_environment_check(orchestrator)

            elif cmd == "4" or cmd == "audit":
                run_full_audit(orchestrator)

            elif cmd == "5" or cmd == "help":
                print_banner()
                print("\n使用说明:")
                print("  1. test - 运行测试用例生成工作流")
                print("  2. code - 对指定文件进行代码审核")
                print("  3. env - 检查当前环境配置")
                print("  4. audit - 运行全能审核（测试用例、代码、环境、安全）")
                print("  5. help - 显示帮助信息")
                print("  6. exit - 退出程序")

            elif cmd == "6" or cmd == "exit":
                print("\n感谢使用！再见！👋\n")
                break

            else:
                print("\n❓ 未知命令，请输入 help 查看可用命令")

        except KeyboardInterrupt:
            print("\n\n程序被中断。再见！👋\n")
            break
        except Exception as e:
            print(f"\n❌ 发生错误: {str(e)}")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="多Agent协同工作系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python multi_agent_runner.py --task test_case --requirement-id 1001345 --requirement-name "客户报价明细导出优化"
  python multi_agent_runner.py --task code_review --file path/to/file.py
  python multi_agent_runner.py --task environment_check
  python multi_agent_runner.py --task full_audit
  python multi_agent_runner.py --interactive
        """,
    )

    parser.add_argument(
        "--task",
        choices=["test_case", "code_review", "environment_check", "full_audit", "interactive"],
        help="任务类型",
    )

    parser.add_argument("--requirement-id", help="需求ID（用于测试用例生成）")

    parser.add_argument("--requirement-name", help="需求名称（用于测试用例生成）")

    parser.add_argument("--file", help="文件路径（用于代码审核）")

    parser.add_argument("--interactive", action="store_true", help="启动交互模式")

    args = parser.parse_args()

    # 打印横幅
    print_banner()

    # 交互模式
    if args.interactive or not args.task:
        interactive_mode()
        return 0

    # 创建编排器
    orchestrator = create_orchestrator()

    # 根据任务类型执行
    if args.task == "test_case":
        if not args.requirement_id or not args.requirement_name:
            print("❌ 请提供 --requirement-id 和 --requirement-name")
            return 2
        run_test_case_generation(orchestrator, args.requirement_id, args.requirement_name)

    elif args.task == "code_review":
        if not args.file:
            print("❌ 请提供 --file 参数")
            return 2
        run_code_review(orchestrator, args.file)

    elif args.task == "environment_check":
        run_environment_check(orchestrator)

    elif args.task == "full_audit":
        run_full_audit(orchestrator)


if __name__ == "__main__":
    sys.exit(main())

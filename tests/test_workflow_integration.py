#!/usr/bin/env python3
"""审核与自动化方案确认工作流集成测试"""

import sys
import time

from modules.trae_test.orchestrator.auto_agent import auto_agent, confirmation_service
from modules.trae_test.orchestrator.workflow_state_machine import WorkflowState, lock_manager, state_machine
from modules.trae_test.utils.excel_generator import ExcelGenerator


def test_excel_export():
    """测试Excel导出功能"""
    print("\n📊 测试一：Excel导出功能")
    print("-" * 40)

    generator = ExcelGenerator()

    test_cases = [
        {
            "用例目录": "销售 - 订单处理",
            "用例名称": "验证订单创建",
            "需求ID": "SO-001",
            "前置条件": "1. 用户已登录\n2. 存在商品数据",
            "用例步骤": "1. 进入订单页面\n2. 填写信息\n3. 提交",
            "预期结果": "订单创建成功",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "高",
            "创建人": "余小龙",
            "优先级": "P1",
            "是否可自动化": "是",
            "回归测试标识": "否",
            "知识库关联": "",
            "质量评分": 95,
        },
        {
            "用例目录": "销售 - 订单处理",
            "用例名称": "验证订单支付",
            "需求ID": "SO-002",
            "前置条件": "1. 有待支付订单\n2. 账户余额充足",
            "用例步骤": "1. 选择订单\n2. 点击支付\n3. 完成支付",
            "预期结果": "支付成功，状态更新",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "高",
            "创建人": "余小龙",
            "优先级": "P0",
            "是否可自动化": "是",
            "回归测试标识": "否",
            "知识库关联": "",
            "质量评分": 95,
        },
    ]

    # 验证用例格式
    try:
        generator._validate_test_cases(test_cases)
        print("用例格式验证: 通过")
    except ValueError as e:
        print(f"用例格式验证: 失败 - {e}")

    # 导出测试
    result = generator.export_cases(test_cases, "test_export.xlsx")
    print(f"导出结果: {'成功' if result['success'] else '失败'}")
    if result["success"]:
        print(f"文件路径: {result['path']}")
        print(f"文件大小: {result['file_size']} bytes")

    assert result["success"]


def test_workflow_state_machine():
    """测试工作流状态机"""
    print("\n🔄 测试二：工作流状态机")
    print("-" * 40)

    class MockWorkflow:
        def __init__(self):
            self.workflow_id = "test_wf_001"
            self.state = WorkflowState.PENDING.value
            self.steps = []
            self.last_state_change = None
            self.timeout_count = 0

    wf = MockWorkflow()

    transitions = [
        ("初始状态", WorkflowState.PENDING),
        ("启动执行", WorkflowState.RUNNING),
        ("用例生成完成", WorkflowState.GENERATED),
        ("进入审核", WorkflowState.AWAITING_REVIEW),
    ]

    for desc, target_state in transitions:
        success = state_machine.transition(wf, target_state)
        print(f"{desc}: {'✅' if success else '❌'} {wf.state}")

    # 测试锁定机制
    lock_manager.auto_lock_on_review(wf)
    print(f"审核状态锁定: {'✅' if lock_manager.is_locked(wf.workflow_id) else '❌'}")

    # 测试审核通过（需要添加测试用例到steps）
    wf.steps.append({"result": [{"审核状态": "APPROVED"}, {"审核状态": "APPROVED"}]})

    success = state_machine.transition(wf, WorkflowState.REVIEWING)
    print(f"进入审核中: {'✅' if success else '❌'}")

    success = state_machine.transition(wf, WorkflowState.AUTO_SOLUTION_GENERATED)
    print(f"审核通过进入方案生成: {'✅' if success else '❌'}")

    assert success


def test_auto_agent():
    """测试AutoAgent自动化方案生成"""
    print("\n🤖 测试三：AutoAgent自动化方案生成")
    print("-" * 40)

    test_cases = [
        {
            "用例编号": "TC-001",
            "用例名称": "验证订单创建",
            "用例类型": "功能测试",
            "优先级": "P1",
            "测试步骤": "1. 进入订单页面\n2. 填写订单信息\n3. 点击提交",
            "预期结果": "订单创建成功",
        },
        {
            "用例编号": "TC-002",
            "用例名称": "验证订单删除",
            "用例类型": "功能测试",
            "优先级": "P1",
            "测试步骤": "1. 选择订单\n2. 点击删除\n3. 确认删除",
            "预期结果": "订单删除成功",
        },
        {
            "用例编号": "TC-003",
            "用例名称": "验证订单支付",
            "用例类型": "功能测试",
            "优先级": "P0",
            "测试步骤": "1. 选择待支付订单\n2. 点击支付\n3. 完成支付",
            "预期结果": "支付成功",
        },
    ]

    # 生成自动化方案
    start_time = time.time()
    solution = auto_agent.generate_solution("test_wf_001", test_cases)
    elapsed = (time.time() - start_time) * 1000

    print(f"方案生成耗时: {elapsed:.2f} ms")
    print(f"可自动化用例: {solution['analysis']['auto_candidate_count']}")
    print(f"高风险用例: {solution['risk_assessment']['high_risk_count']}")
    print(f"预计执行时间: {solution['analysis']['estimated_execution_time_minutes']} 分钟")

    # 测试二次确认机制
    confirm_result = confirmation_service.confirm_solution("test_wf_001", True, "方案可行，同意执行")
    print(f"方案确认: {'✅' if confirm_result['success'] else '❌'}")

    # 生成报告
    report = auto_agent.generate_markdown_report(solution)
    with open("auto_solution_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print("方案报告已生成")

    assert elapsed < 30000  # 要求30秒内完成


def test_audit_logs():
    """测试审计日志系统（使用AuditAgent内置日志）"""
    print("\n📝 测试四：审计日志系统")
    print("-" * 40)

    from modules.trae_test.orchestrator.audit_agent_enhanced import AuditType, audit_agent

    from modules.trae_test.orchestrator.auditors.test_case_auditor import TestCaseAuditor

    required_fields = TestCaseAuditor.REQUIRED_FIELDS
    valid_test_cases = [
        dict(
            zip(
                required_fields,
                [
                    "维护 - 日志 - 操作日志",
                    "测试审计日志",
                    "REQ-AUDIT-001",
                    "1. 测试人员已登录ERP系统并拥有测试用例审核权限\n2. 审计日志功能已启用且存在可写入的运行环境",
                    "1. 进入测试管理页面\n2. 点击测试用例审核页面的审核入口按钮\n3. 在审核页面提交待审核用例并点击确认审核按钮",
                    "1. 页面显示测试用例审核入口并可正常打开\n2. 系统提示审核提交成功并记录审核结果",
                    "功能测试",
                    "正常",
                    "中",
                    "余小龙",
                    "P1",
                    "是",
                    "",
                    "销售订单 审核日志 测试用例 审核权限 页面入口 提交 记录 结果 业务规则",
                    95,
                ],
            )
        )
    ]
    valid_test_cases[0]["execution_count"] = 20

    result = audit_agent.audit(valid_test_cases, AuditType.TEST_CASE)
    print(f"审核结果: {'通过' if result.passed else '未通过'}")
    print(f"审核日志数: {len(audit_agent.audit_logs)}")

    assert result.passed


def main():
    """运行所有测试"""
    print("=" * 60)
    print("审核与自动化方案确认工作流集成测试")
    print("=" * 60)

    tests = [
        ("Excel导出", test_excel_export),
        ("工作流状态机", test_workflow_state_machine),
        ("AutoAgent方案生成", test_auto_agent),
        ("审计日志系统", test_audit_logs),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            test_func()
            passed += 1
            print(f"\n✅ {name}: 通过")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name}: 异常 - {e}")

    print("\n" + "=" * 60)
    print(f"测试结果: {passed}/{len(tests)} 通过")
    print("=" * 60)

    if failed == 0:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())

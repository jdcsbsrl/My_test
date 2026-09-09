"""Counterexamples for trustworthy results and bounded case maintenance."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.auto_test.core.regression_checks import DataNotReady, QueryCheck, order_rows, verify_query
from modules.auto_test.pages.base_page import BasePage
from modules.trae_test.utils.case_generation_service import CaseGenerationService, apply_field_policy
from modules.trae_test.utils.case_registry import CaseRegistry
from modules.trae_test.utils.runtime_quality import RuntimeQualitySnapshot, attach_runtime_quality
from modules.trae_test.utils.template_builder import ALL_FIELDS
from modules.trae_test.utils.test_case_strategy import TestCaseOptimizer as Optimizer, TestCaseScoreEngine as Scorer
from tools.report_generator import TestReportGenerator as Report


def sample_case():
    case = {field: "示例" for field in ALL_FIELDS}
    case.update({"用例名称": "订单查询正常场景", "质量评分": 40.0, "用例状态": "正常", "需求ID": "REQ-DEMO"})
    attach_runtime_quality(case, RuntimeQualitySnapshot(final_score=40, final_audit_passed=True))
    return case


def test_http_success_does_not_prove_filter_correctness():
    response = SimpleNamespace(
        status_code=200, json=lambda: {"code": 200, "data": {"records": [{"orderNo": "DEMO-B", "orderStatus": "done"}]}}
    )
    with pytest.raises(AssertionError, match="predicate"):
        verify_query(order_rows(response), QueryCheck("exact", {"orderNo": "DEMO-A"}))


def test_empty_or_malformed_results_are_not_passes():
    with pytest.raises(DataNotReady):
        verify_query([], QueryCheck("filter", {}))
    with pytest.raises(AssertionError):
        order_rows(SimpleNamespace(status_code=200, json=lambda: {"code": 200, "data": {}}))


@pytest.mark.parametrize("status", ["SKIP", "BLOCKED"])
def test_unexecuted_report_is_incomplete(status):
    report = Report()
    report.add_test_result("核心场景", status)
    assert report.exit_code == 2
    assert "验证不完整" in report.generate_html_report()
    assert report.summary()["executed"] == 0


def test_missing_planned_checks_are_incomplete():
    report = Report()
    report.planned_count = 2
    report.add_test_result("one", "PASS")
    assert report.exit_code == 2


def test_wait_failure_propagates_when_healing_fails():
    page = BasePage.__new__(BasePage)
    page.page = Mock()
    page.page.locator.return_value.wait_for.side_effect = RuntimeError("missing")
    page.self_healing = SimpleNamespace(enabled=True, execute=lambda *a, **kw: False)
    with pytest.raises(RuntimeError, match="missing"):
        page.wait_for_element("#missing")


def test_fixed_fields_are_not_provider_controlled():
    rules = {
        "用例状态": {"valid_values": ["正常"]},
        "创建人": {"valid_values": ["甲", "乙"], "default_value": "甲", "fixed": True},
    }
    case = {"用例状态": "待审核", "创建人": "乙"}
    apply_field_policy(case, rules)
    assert case == {"用例状态": "正常", "创建人": "甲"}


def test_score_does_not_reward_history_priority_or_padding():
    case = sample_case()
    changed = deepcopy(case)
    changed.update({"execution_count": 100, "优先级": "P0", "知识库关联": "很长" * 100, "用例步骤": "通用句子\n" * 20})
    assert Scorer().score(case) == Scorer().score(changed)


def test_optimizer_never_invents_expected_results():
    case = {"用例步骤": "1. 输入数量0", "预期结果": "", "用例名称": "短名"}
    original = deepcopy(case)
    Optimizer().optimize(case)
    assert case == original


def test_retrieval_error_is_not_a_default_case():
    retriever = Mock()
    retriever.retrieve.side_effect = RuntimeError("backend failed")
    service = CaseGenerationService(retriever=retriever, gateway=Mock(), rules={})
    with pytest.raises(RuntimeError, match="backend failed"):
        service.generate("查询规则", "REQ-DEMO")


def test_missing_knowledge_produces_one_batch_question():
    retriever = Mock()
    retriever.retrieve.return_value = []
    retriever.search_business_rules.return_value = []
    result = CaseGenerationService(retriever=retriever, gateway=Mock(), rules={}).generate("规则", "REQ")
    assert not result["cases"] and len(result["questions"]) == 1


def test_registration_reuses_content_and_preserves_versions(tmp_path):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    case = sample_case()
    case_id, version = registry.save(case, "REQ-DEMO")
    assert registry.save(case, "REQ-DEMO") == (case_id, version)
    changed = deepcopy(case)
    changed["预期结果"] = "列表显示新的查询结果"
    with pytest.raises(ValueError, match="Existing title"):
        registry.save(changed, "REQ-DEMO")
    assert registry.save(changed, "REQ-DEMO", case_id=case_id, reason="规则更新") == (case_id, 2)
    assert len(registry.list_cases(active_only=False)) == 2
    assert len(registry.list_cases()) == 1
    registry.record_execution(case_id, 1, "PASS", "old-run")
    registry.retire(case_id, "需求下线")
    assert not registry.list_cases()
    assert len(registry.list_cases(active_only=False)) == 2


def test_registry_rejects_unaudited_cases(tmp_path):
    case = sample_case()
    case["_runtime_quality"]["final_audit_passed"] = False
    with pytest.raises(ValueError, match="audited"):
        CaseRegistry(tmp_path / "cases.sqlite3").save(case, "REQ-DEMO")


def test_binding_script_creates_traceable_version(tmp_path):
    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    case = sample_case()
    case_id, version = registry.save(case, "REQ-DEMO")
    registry.record_execution(case_id, version, "FAIL", "first-run")
    assert registry.save(
        case,
        "REQ-DEMO",
        case_id=case_id,
        reason="关联脚本",
        script_id="modules/auto_test/tests/test_login_regression.py::test_demo",
    ) == (case_id, 2)
    history = registry.list_cases(active_only=False)
    assert history[0]["last_status"] == "FAIL"
    assert history[1]["last_status"] is None


def test_grounded_new_case_can_pass_without_execution_history(monkeypatch):
    from modules.trae_test.orchestrator.audit_gateway import AuditGateway
    from modules.trae_test.orchestrator.audit_rules import RuleManager
    from modules.trae_test.utils import dir_validator

    monkeypatch.setattr(dir_validator, "_load_module_hierarchy", lambda: {"销售": {"订单": ["查询"]}})
    case = sample_case()
    case.update(
        {
            "用例目录": "销售 - 订单 - 查询",
            "用例名称": "销售订单查询状态筛选",
            "前置条件": "1. 用户已登录并拥有订单查询权限\n2. 系统存在状态为待审核的订单数据",
            "用例步骤": "1. 进入订单查询页面\n2. 在状态字段选择测试数据：待审核\n3. 点击查询按钮",
            "预期结果": "1. 页面显示订单查询列表\n2. 列表订单状态均为待审核",
            "用例类型": "功能测试",
            "用例等级": "高",
            "创建人": "余小龙",
            "优先级": "P1",
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "状态筛选仅返回匹配状态的订单",
        }
    )
    retriever = Mock()
    retriever.retrieve.return_value = [{"id": "R1", "content": {"rule_description": case["知识库关联"]}}]
    provider = Mock()
    provider.generate_case.return_value = case
    service = CaseGenerationService(
        retriever=retriever,
        gateway=AuditGateway(),
        rules=RuleManager.default_field_value_rules(),
        provider_factory=lambda **kwargs: provider,
    )
    result = service.generate("订单状态筛选", "REQ-DEMO")
    assert result["status"] == "ready", result["questions"]
    assert not result["questions"]
    assert result["cases"][0]["_runtime_quality"]["is_cold_start"] is True
    assert set(result["cases"][0]) - set(ALL_FIELDS) == {"_runtime_quality", "_runtime_quality_version"}


def test_selection_does_not_omit_related_p0(tmp_path):
    from modules.auto_test.core.registered_regression import plan_registered_cases

    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    p0 = sample_case()
    p0["优先级"] = "P0"
    script = "modules/auto_test/tests/test_registered_query_smoke.py::test_sales_order_query_smoke"
    p0_id, _ = registry.save(p0, "REQ-DEMO", script_id=script)
    p1 = sample_case()
    p1.update({"优先级": "P1", "用例名称": "异常边界"})
    case_id, _ = registry.save(p1, "REQ-DEMO", script_id=script)
    selected = plan_registered_cases(registry, [case_id])
    assert [row["case_id"] for row in selected] == [case_id, p0_id]


def test_selection_rejects_non_test_script(tmp_path):
    from modules.auto_test.core.registered_regression import plan_registered_cases

    registry = CaseRegistry(tmp_path / "cases.sqlite3")
    case_id, _ = registry.save(sample_case(), "REQ-DEMO", script_id="tools/report_generator.py::main")
    with pytest.raises(ValueError, match="pytest node"):
        plan_registered_cases(registry, [case_id])


def test_registered_run_does_not_treat_all_skipped_xml_as_pass(tmp_path, monkeypatch):
    import modules.auto_test.core.registered_regression as runner
    import modules.auto_test.core.config_manager as config
    import modules.auto_test.core.execution_auth as auth

    monkeypatch.setattr(auth, "check_authorization", lambda: None)
    monkeypatch.setattr(config, "get_environment", lambda env: None)
    monkeypatch.setattr(runner, "runtime_dir", lambda kind: tmp_path)

    def run(command, **kwargs):
        from pathlib import Path

        destination = Path(next(arg.split("=", 1)[1] for arg in command if arg.startswith("--junitxml=")))
        destination.write_text(
            '<testsuites><testsuite><testcase name="x"><skipped/></testcase></testsuite></testsuites>'
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(runner.subprocess, "run", run)
    registry = Mock()
    result = runner.run_registered_cases(
        registry, [{"case_id": "TC-DEMO", "version": 2, "script_id": "unused::test_demo"}], "test"
    )
    assert result == 2
    assert registry.record_execution.call_args.args[:3] == ("TC-DEMO", 2, "BLOCKED")


def test_query_runner_detects_ignored_filters():
    from modules.auto_test.core.regression_checks import execute_sales_queries

    rows = [{"orderNo": "DEMO-A", "orderStatus": "new"} for _ in range(5)] + [
        {"orderNo": "DEMO-B", "orderStatus": "done"} for _ in range(5)
    ]
    facade = Mock()
    facade.query_orders.return_value = SimpleNamespace(status_code=200, json=lambda: {"code": 200, "data": rows})
    report = Report()
    execute_sales_queries(facade, report)
    assert report.exit_code == 1
    assert [row["status"] for row in report.results] == ["PASS", "FAIL", "FAIL", "FAIL", "FAIL", "FAIL", "FAIL"]


def test_harness_core_skip_changes_success_exit_code(tmp_path, monkeypatch):
    import fixtures.harness_plugin as plugin

    state = {
        "results": [{"nodeid": "core-test", "outcome": "skipped", "critical": True}],
        "attempts": {},
        "metrics": None,
    }
    monkeypatch.setattr(plugin, "_state", lambda config: state)
    monkeypatch.setattr(plugin, "_ensure_runtime_directories", lambda config: None)
    monkeypatch.setattr(plugin, "_runtime_reports_dir", lambda config: tmp_path)
    session = SimpleNamespace(config=SimpleNamespace(), exitstatus=0, testscollected=1)
    plugin.pytest_sessionfinish(session, 0)
    assert session.exitstatus == 2

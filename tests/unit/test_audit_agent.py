"""AuditAgent 单元测试"""

import pytest

from modules.trae_test.orchestrator.audit_agent_enhanced import (
    AuditAgent,
    AuditFailedException,
    AuditResult,
    AuditType,
    OperationType,
)
from modules.trae_test.orchestrator.config import AuditConfig


class TestAuditResult:
    def test_init(self):
        r = AuditResult()
        assert r.passed is True
        assert r.errors == []

    def test_add_error(self):
        r = AuditResult()
        r.add_error("ERR", "msg", "loc")
        assert r.passed is False
        assert len(r.errors) == 1

    def test_add_warning(self):
        r = AuditResult()
        r.add_error("WRN", "msg", severity="warning")
        assert r.passed is True
        assert len(r.warnings) == 1

    def test_to_dict(self):
        r = AuditResult()
        d = r.to_dict()
        assert "passed" in d
        assert "errors" in d


class TestOperationType:
    def test_from_context(self):
        assert OperationType.from_context({"action": "generate", "target": "code"}) == OperationType.CODE_GENERATION
        assert OperationType.from_context({"action": "create", "target": "folder"}) == OperationType.FOLDER_CREATION
        assert OperationType.from_context({"action": "unknown"}) == OperationType.UNKNOWN


class TestAuditAgentInit:
    def test_default_init(self):
        agent = AuditAgent()
        assert agent.config is not None
        assert agent.audit_logs == []

    def test_custom_config(self):
        config = AuditConfig(enforce_hard_block=False)
        agent = AuditAgent(config=config)
        assert agent.config.enforce_hard_block is False


class TestAuditAgentTestCases:
    @staticmethod
    def _valid_case(**runtime):
        case = {
            "用例目录": "产品 - 产品中心 - 库存SKU",
            "用例名称": "库存SKU业务规则验证",
            "需求ID": "REQ-COVERAGE-001",
            "前置条件": "1. 用户已登录ERP系统并拥有库存SKU权限\n2. 系统中存在可操作的库存SKU数据",
            "用例步骤": "1. 进入库存SKU页面\n2. 点击业务操作按钮\n3. 在页面提交测试数据并查看结果",
            "预期结果": "1. 页面显示库存SKU列表\n2. 系统显示处理结果",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "高",
            "创建人": "余小龙",
            "优先级": "P0",
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "库存SKU 页面 业务规则 操作 结果",
            "质量评分": 95,
        }
        case.update(runtime)
        return case

    def test_requirement_coverage_blocks_missing_rule(self):
        agent = AuditAgent()
        result = agent.audit_test_cases(
            [self._valid_case(**{"覆盖规则ID": "R1", "场景类型": "正常"})],
            {"coverage_matrix": [{"id": "R1", "priority": "P0"}, {"id": "R2", "priority": "P1"}]},
        )
        assert result.passed is False
        assert any(i.rule_id == "REQ_COVERAGE_INCOMPLETE" for i in result.issues)

    def test_requirement_coverage_matrix_required_when_enabled(self):
        agent = AuditAgent()
        result = agent.audit_test_cases([self._valid_case()], {"require_requirement_coverage": True})
        assert result.passed is False
        assert any(i.rule_id == "REQ_COVERAGE_MATRIX_MISSING" for i in result.issues)

    def test_runtime_coverage_matrix_is_consumed(self):
        agent = AuditAgent()
        case = self._valid_case(
            **{
                "_runtime_coverage_matrix": {"business_rules": ["RUNTIME-R1"], "normal_scenarios": ["正常"]},
                "覆盖规则ID": "RUNTIME-R1",
                "场景类型": "正常",
                "优先级": "P1",
            }
        )
        result = agent.audit_test_cases([case], {"require_requirement_coverage": True})
        assert result.passed is True

    def test_requirement_p0_missing_scenario_blocks(self):
        agent = AuditAgent()
        result = agent.audit_test_cases(
            [self._valid_case(**{"覆盖规则ID": "R1", "场景类型": "正常"})],
            {"coverage_matrix": [{"id": "R1", "priority": "P0", "required_scenarios": ["正常", "异常"]}]},
        )
        assert result.passed is False
        assert any(i.rule_id == "REQ_P0_SCENARIO_MISSING" for i in result.issues)

    def test_rollback_missing_blocks_when_required(self):
        agent = AuditAgent()
        result = agent.audit_test_cases(
            [self._valid_case(**{"覆盖规则ID": "R1", "场景类型": "正常", "回滚标识": "否"})],
            {"coverage_matrix": [{"id": "R1", "priority": "P1"}], "requires_rollback": True},
        )
        assert result.passed is False
        assert any(i.rule_id == "REQ_ROLLBACK_SCENARIO_MISSING" for i in result.issues)

    def test_excluded_scope_blocks(self):
        agent = AuditAgent()
        result = agent.audit_test_cases(
            [self._valid_case(**{"覆盖规则ID": "R1", "场景类型": "正常", "模块": "WMS"})],
            {"coverage_matrix": [{"id": "R1", "priority": "P1"}], "excluded_scope": ["WMS"]},
        )
        assert result.passed is False
        assert any(i.rule_id == "REQ_SCOPE_BOUNDARY_VIOLATION" for i in result.issues)

    def test_requirement_coverage_passes_with_required_scenarios_and_rollback(self):
        agent = AuditAgent()
        cases = [
            self._valid_case(**{"覆盖规则ID": "R1", "场景类型": "正常", "回滚标识": "否"}),
            self._valid_case(**{"覆盖规则ID": "R1", "场景类型": "异常", "回滚标识": "是"}),
        ]
        result = agent.audit_test_cases(
            cases,
            {
                "coverage_matrix": [{"id": "R1", "priority": "P0", "required_scenarios": ["正常", "异常"]}],
                "requires_rollback": True,
            },
        )
        assert result.passed is True
        assert any("需求规则覆盖率：100%" in s for s in result.suggestions)

    def test_empty_list(self):
        agent = AuditAgent()
        r = agent.audit_test_cases([])
        assert r.passed is False

    def test_invalid_type(self):
        agent = AuditAgent()
        r = agent.audit_test_cases("not list")
        assert r.passed is True

    def test_valid_cases(self):
        agent = AuditAgent()
        cases = [
            {
                "用例目录": "产品 - 产品中心 - 库存SKU",
                "用例名称": "销售订单创建成功流程验证",
                "需求ID": "1",
                "前置条件": "1. 用户已登录ERP系统并拥有订单权限\n2. 系统中存在可用测试商品",
                "用例步骤": "1. 进入销售订单页面\n2. 点击新建订单按钮\n3. 选择测试商品并提交订单",
                "预期结果": "1. 页面打开并显示新建订单按钮\n2. 订单提交成功并生成订单号",
                "用例类型": "功能测试",
                "用例状态": "正常",
                "用例等级": "高",
                "创建人": "余小龙",
                "优先级": "P0",
                "是否可自动化": "是",
                "回归测试标识": "是",
                "知识库关联": "销售订单 客户 商品 库存 数量 价格 权限 状态 提交 校验 业务规则",
                "质量评分": 95,
                "execution_count": 20,
            }
        ]
        r = agent.audit_test_cases(cases)
        assert r.passed is True

    def test_missing_fields(self):
        agent = AuditAgent()
        cases = [{"用例名称": "test"}]
        r = agent.audit_test_cases(cases)
        assert r.passed is False

    def test_invalid_directory_is_blocking(self):
        agent = AuditAgent()
        case = {
            "用例目录": "库存SKU",
            "用例名称": "库存SKU目录校验",
            "需求ID": "REQ-DIR-001",
            "前置条件": "1. 用户已登录ERP系统\n2. 用户拥有库存SKU权限",
            "用例步骤": "1. 进入库存SKU页面\n2. 点击批量加入采购计划按钮\n3. 查看弹窗",
            "预期结果": "1. 页面显示库存SKU\n2. 弹窗正常打开",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "中",
            "创建人": "余小龙",
            "优先级": "P1",
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "库存SKU 产品中心 页面",
            "质量评分": 95,
        }
        result = agent.audit_test_cases([case])
        assert result.passed is False
        assert any(issue.rule_id == "TC_DIRECTORY_INVALID" for issue in result.issues)

    def test_score_source_mismatch_blocks_and_normalizes_only_consistent_scores(self):
        agent = AuditAgent()
        case = {
            "用例目录": "测试用例/销售",
            "用例名称": "销售订单提交结果验证",
            "需求ID": "REQ-SCORE-001",
            "前置条件": "1. 用户已登录ERP系统并拥有订单权限\n2. 系统中存在可提交订单",
            "用例步骤": "1. 进入销售订单页面\n2. 点击新建订单按钮\n3. 填写订单信息并提交",
            "预期结果": "1. 页面显示销售订单页面\n2. 提交成功并生成订单号",
            "用例类型": "功能测试",
            "用例状态": "正常",
            "用例等级": "中",
            "创建人": "测试人员",
            "优先级": "P1",
            "是否可自动化": "是",
            "回归测试标识": "是",
            "知识库关联": "销售订单 页面 提交 订单号 业务规则",
            "最终评分": 92,
            "质量评分": 88,
        }
        result = agent.audit_test_cases([case])
        assert result.passed is False
        assert any(issue.rule_id == "TC_SCORE_SOURCE_MISMATCH" for issue in result.issues)


class TestAuditAgentCode:
    def test_empty_code(self):
        agent = AuditAgent()
        r = agent.audit_code("")
        assert r.passed is False

    def test_invalid_type(self):
        agent = AuditAgent()
        r = agent.audit_code(123)
        assert r.passed is False

    def test_valid_python(self):
        agent = AuditAgent()
        r = agent.audit_code("def test(): pass")
        assert r.passed is True

    def test_future_import_is_not_reported_as_private(self):
        agent = AuditAgent()
        result = agent.audit_code("from __future__ import annotations")
        assert all(issue.rule_id != "CODE_PRIVATE_IMPORT" for issue in result.issues)

    def test_syntax_error(self):
        agent = AuditAgent()
        r = agent.audit_code("def test(")
        assert r.passed is False


class TestAuditAgentSecurity:
    def test_password_pattern(self):
        agent = AuditAgent()
        r = agent.audit_security('password = "secret"')
        assert r.passed is False

    def test_api_key_pattern(self):
        agent = AuditAgent()
        r = agent.audit_security('api_key = "sk-123"')
        assert r.passed is False

    def test_no_risk(self):
        agent = AuditAgent()
        r = agent.audit_security("def safe(): pass")
        assert r.passed is True


class TestAuditAgentEnvironment:
    def test_empty_config(self):
        agent = AuditAgent()
        r = agent.audit_environment({})
        assert r.passed is True

    def test_valid_config(self):
        agent = AuditAgent()
        r = agent.audit_environment({"python_version": "3.12", "dependencies": []})
        assert r.passed is True

    def test_missing_keys(self):
        agent = AuditAgent()
        r = agent.audit_environment({"test": "value"})
        assert r.passed is True


class TestAuditAgentImpact:
    def test_core_file(self):
        agent = AuditAgent()
        r = agent.audit_impact([], {"file_path": "core/config_manager.py"})
        assert r.passed is True

    def test_many_files(self):
        agent = AuditAgent()
        r = agent.audit_impact(list(range(15)), {"file_path": "test.py"})
        assert r.passed is True


class TestAuditAgentGeneric:
    def test_audit_types(self):
        agent = AuditAgent()
        r = agent.audit("code", AuditType.CODE)
        assert r.audit_type == AuditType.CODE
        assert r.passed is True

    def test_unknown_type(self):
        config = AuditConfig(enforce_hard_block=False)
        agent = AuditAgent(config=config)
        normalized = agent._normalize_audit_type("UNKNOWN")
        assert normalized == AuditType.ALL

    def test_needs_approval(self):
        agent = AuditAgent()
        assert agent._needs_approval({"action": "generate", "target": "code"}) is True
        assert agent._needs_approval({"action": "read"}) is False

    def test_generate_report(self):
        agent = AuditAgent()
        agent.audit("test", AuditType.CODE)
        report = agent.generate_report()
        assert "审核报告" in report

    def test_get_summary(self):
        agent = AuditAgent()
        agent.audit("test", AuditType.CODE)
        s = agent.get_audit_summary()
        assert s["total_audits"] == 1


class TestAuditAgentHardBlock:
    def test_hard_block(self):
        config = AuditConfig(enforce_hard_block=True)
        agent = AuditAgent(config=config)
        with pytest.raises(AuditFailedException):
            agent.audit([], AuditType.TEST_CASE)

    def test_hard_block_disabled(self):
        config = AuditConfig(enforce_hard_block=False)
        agent = AuditAgent(config=config)
        r = agent.audit([], AuditType.TEST_CASE)
        assert r.passed is False

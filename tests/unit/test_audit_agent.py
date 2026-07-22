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
                "用例目录": "测试用例/销售",
                "用例名称": "test",
                "需求ID": "1",
                "前置条件": "pre",
                "用例步骤": "step",
                "预期结果": "exp",
                "用例类型": "功能测试",
                "用例状态": "正常",
                "用例等级": "高",
                "创建人": "余小龙",
                "优先级": "P0",
                "是否可自动化": "是",
                "关联缺陷ID": "",
                "回归测试标识": "是",
                "知识库关联": "kb",
            }
        ]
        r = agent.audit_test_cases(cases)
        assert r.passed is True

    def test_missing_fields(self):
        agent = AuditAgent()
        cases = [{"用例名称": "test"}]
        r = agent.audit_test_cases(cases)
        assert r.passed is False


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

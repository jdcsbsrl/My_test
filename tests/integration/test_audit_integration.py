"""审核Agent集成测试 - 验证审核流程在工作流执行中被正确调用"""

from unittest.mock import Mock

import pytest

from modules.trae_test.orchestrator.agent_orchestrator import AgentOrchestrator
from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent, AuditResult
from modules.trae_test.orchestrator.workflow_manager import (
    AuditType,
    StepStatus,
    StepType,
    WorkflowManager,
    WorkflowStep,
)


class TestAuditAgentIntegration:
    """验证审核Agent在工作流执行中被正确调用"""

    def test_audit_called_on_workflow_execution(self):
        """测试工作流执行时审核Agent被调用"""
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test")

        step = WorkflowStep(step_id="s1", name="test_step", step_type=StepType.AGENT, audit_type=AuditType.CODE)
        wf.add_step(step)

        mock_auditor = Mock(spec=AuditAgent)
        mock_result = AuditResult()
        mock_result.passed = True
        mock_auditor.audit.return_value = mock_result

        def executor(step, prev):
            return "test_result"

        mgr.execute_workflow(workflow_id=wf.workflow_id, executor=executor, auditor=mock_auditor)

        mock_auditor.audit.assert_called_once()
        call_args = mock_auditor.audit.call_args
        assert call_args[1]["target"] == "test_result"
        assert call_args[1]["audit_type"] == AuditType.CODE

    def test_audit_fail_stops_workflow(self):
        """测试审核失败时工作流步骤被标记为失败"""
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test")

        step = WorkflowStep(
            step_id="s1", name="test_step", step_type=StepType.AGENT, audit_type=AuditType.CODE, max_retries=0
        )
        wf.add_step(step)

        mock_auditor = Mock(spec=AuditAgent)
        mock_result = AuditResult()
        mock_result.passed = False
        mock_result.errors = [{"code": "ERR", "message": "failed"}]
        mock_auditor.audit.return_value = mock_result

        def executor(step, prev):
            return "bad_result"

        mgr.execute_workflow(workflow_id=wf.workflow_id, executor=executor, auditor=mock_auditor)

        assert step.status == StepStatus.FAILED
        assert step.audit_result.passed is False

    def test_audit_agent_always_called_in_orchestrator(self):
        """测试编排器执行工作流时审核Agent被调用"""
        orchestrator = AgentOrchestrator()
        audit_called = []

        original_audit = orchestrator.audit_agent.audit

        def track_audit(*args, **kwargs):
            audit_called.append((args, kwargs))
            result = AuditResult()
            result.passed = True
            return result

        orchestrator.audit_agent.audit = track_audit

        class TestAgent:
            def execute(self, **kwargs):
                return "test_output"

        orchestrator.register_agent("test_agent", TestAgent())

        workflow_def = {
            "name": "test_workflow",
            "steps": [
                {
                    "step_id": "s1",
                    "name": "test_step",
                    "type": "AGENT",
                    "agent_type": "test_agent",
                    "audit_type": "CODE",
                }
            ],
        }

        orchestrator.execute_workflow(workflow_def)

        assert len(audit_called) == 1
        audit_type_arg = audit_called[0][1]["audit_type"]
        assert audit_type_arg == AuditType.CODE or str(audit_type_arg) == "CODE"

    def test_hard_block_enforcement(self):
        """测试硬阻断机制生效 - 直接测试审核Agent抛出异常"""
        from modules.trae_test.orchestrator.audit_agent_enhanced import AuditFailedException
        from modules.trae_test.orchestrator.config import AuditConfig

        audit_config = AuditConfig(enforce_hard_block=True)
        agent = AuditAgent(config=audit_config)

        mock_result = AuditResult()
        mock_result.passed = False
        mock_result.errors = [{"code": "SEC", "message": "security risk", "severity": "blocker", "location": ""}]

        with pytest.raises(AuditFailedException):
            agent._handle_audit_failure(mock_result, AuditType.SECURITY)

    def test_hard_block_propagates_in_workflow(self):
        """测试工作流中硬阻断异常正确传播"""
        from modules.trae_test.orchestrator.audit_agent_enhanced import AuditFailedException

        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test")

        step = WorkflowStep(
            step_id="s1", name="test_step", step_type=StepType.AGENT, audit_type=AuditType.CODE, max_retries=0
        )
        wf.add_step(step)

        mock_auditor = Mock(spec=AuditAgent)
        mock_auditor.audit.side_effect = AuditFailedException("hard block triggered")

        def executor(step, prev):
            return "result"

        with pytest.raises(AuditFailedException):
            mgr.execute_workflow(workflow_id=wf.workflow_id, executor=executor, auditor=mock_auditor)

    def test_audit_coverage_in_workflow(self):
        """测试工作流中每个步骤都被审核"""
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="multi_step")

        steps = [
            WorkflowStep(step_id="s1", name="step1", step_type=StepType.AGENT, audit_type=AuditType.CODE),
            WorkflowStep(step_id="s2", name="step2", step_type=StepType.AGENT, audit_type=AuditType.SECURITY),
            WorkflowStep(step_id="s3", name="step3", step_type=StepType.AGENT, audit_type=AuditType.TEST_CASE),
        ]
        for step in steps:
            wf.add_step(step)

        mock_auditor = Mock(spec=AuditAgent)
        mock_result = AuditResult()
        mock_result.passed = True
        mock_auditor.audit.return_value = mock_result

        def executor(step, prev):
            return f"result_{step.step_id}"

        mgr.execute_workflow(workflow_id=wf.workflow_id, executor=executor, auditor=mock_auditor)

        assert mock_auditor.audit.call_count == 3

        call_args_list = mock_auditor.audit.call_args_list
        assert call_args_list[0][1]["audit_type"] == AuditType.CODE
        assert call_args_list[1][1]["audit_type"] == AuditType.SECURITY
        assert call_args_list[2][1]["audit_type"] == AuditType.TEST_CASE

    def test_audit_logging_enabled(self):
        """测试审核日志被记录"""
        from modules.trae_test.orchestrator.config import AuditConfig

        config = AuditConfig(detailed_logging=True)
        agent = AuditAgent(config=config)

        result = agent.audit("test", AuditType.CODE)

        assert len(agent.audit_logs) == 1
        log_entry = agent.audit_logs[0]
        audit_type_in_log = log_entry.get("audit_type", "")
        assert audit_type_in_log == "code" or audit_type_in_log == AuditType.CODE


class TestAuditAgentReliability:
    """审核Agent可靠性测试"""

    def test_audit_agent_not_none_in_orchestrator(self):
        """测试编排器中审核Agent不为None"""
        orchestrator = AgentOrchestrator()
        assert orchestrator.audit_agent is not None

    def test_audit_agent_init_with_config(self):
        """测试审核Agent使用配置初始化"""
        from modules.trae_test.orchestrator.config import AuditConfig

        config = AuditConfig(enforce_hard_block=True, enabled=True, strict_level=3)
        agent = AuditAgent(config=config)

        assert agent.config.enforce_hard_block is True
        assert agent.config.enabled is True
        assert agent.config.strict_level == 3

    def test_audit_disabled_bypasses_check(self):
        """测试禁用审核时跳过检查"""
        from modules.trae_test.orchestrator.config import AuditConfig

        config = AuditConfig(enabled=False)
        agent = AuditAgent(config=config)

        result = agent.audit("anything", "CODE")

        assert result.passed is True
        assert result.errors == []

    def test_audit_always_returns_result(self):
        """测试审核总是返回结果对象（禁用硬阻断模式）"""
        from modules.trae_test.orchestrator.config import AuditConfig
        config = AuditConfig(enforce_hard_block=False)
        agent = AuditAgent(config=config)

        result = agent.audit(None, None)

        assert isinstance(result, AuditResult)
        assert hasattr(result, "passed")
        assert hasattr(result, "errors")

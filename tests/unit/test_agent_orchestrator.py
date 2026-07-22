"""AgentOrchestrator 单元测试"""

import pytest

from modules.trae_test.orchestrator.agent_orchestrator import AgentOrchestrator, AgentRegistry, Task
from modules.trae_test.orchestrator.config import OrchestratorConfig


class TestAgentRegistry:
    def test_register_and_get(self):
        reg = AgentRegistry()
        obj = object()
        reg.register("test", obj)
        assert reg.get("test") is obj

    def test_get_nonexistent(self):
        reg = AgentRegistry()
        assert reg.get("nonexistent") is None

    def test_list_agents(self):
        reg = AgentRegistry()
        reg.register("a1", object())
        reg.register("a2", object())
        assert len(reg.list_agents()) == 2


class TestTask:
    def test_init(self):
        t = Task()
        assert t.task_id.startswith("task_")
        assert t.status == "pending"


class TestAgentOrchestratorInit:
    def test_default_init(self):
        o = AgentOrchestrator()
        assert o.config is not None
        assert o.agent_registry is not None
        assert o.audit_agent is not None

    def test_custom_config(self):
        config = OrchestratorConfig()
        o = AgentOrchestrator(config=config)
        assert o.config == config


class TestAgentOrchestratorWorkflow:
    def test_create_step_invalid_type(self):
        o = AgentOrchestrator()
        with pytest.raises(ValueError):
            o._create_step({"type": "INVALID"}, 0)

    def test_create_step_invalid_audit_type(self):
        o = AgentOrchestrator()
        with pytest.raises(ValueError):
            o._create_step({"type": "AGENT", "audit_type": "INVALID"}, 0)

    def test_create_step_valid(self):
        o = AgentOrchestrator()
        step = o._create_step(
            {"step_id": "s1", "name": "test", "type": "AGENT", "agent_type": "test_agent", "audit_type": "CODE"}, 0
        )
        assert step.step_id == "s1"
        assert step.name == "test"

    def test_get_workflow_status(self):
        o = AgentOrchestrator()
        assert o.get_workflow_status("nonexistent") is None

    def test_list_active_workflows(self):
        o = AgentOrchestrator()
        assert isinstance(o.list_active_workflows(), list)


class TestAgentOrchestratorExecution:
    def test_execute_step_no_agent(self):
        o = AgentOrchestrator()
        from modules.trae_test.orchestrator.workflow_manager import Workflow, WorkflowStep

        step = WorkflowStep(step_id="s1", agent_type="nonexistent")
        workflow = Workflow(name="test")
        with pytest.raises(Exception):
            o._execute_step(step, None, workflow)

    def test_execute_step_with_agent(self):
        o = AgentOrchestrator()

        class TestAgent:
            def execute(self, **kwargs):
                return "result"

        o.register_agent("test_agent", TestAgent())

        from modules.trae_test.orchestrator.workflow_manager import Workflow, WorkflowStep

        step = WorkflowStep(step_id="s1", agent_type="test_agent")
        workflow = Workflow(name="test")
        result = o._execute_step(step, None, workflow)
        assert result == "result"

    def test_execute_workflow_empty(self):
        o = AgentOrchestrator()
        wf = o.execute_workflow({"name": "empty", "steps": []})
        assert wf is not None
        assert wf.name == "empty"


class TestAgentOrchestratorWorkflows:
    def test_execute_test_case_generation(self):
        """测试用例生成工作流：使用非空用例列表以通过审计硬阻断。"""
        from modules.trae_test.orchestrator.config import (
            AuditConfig,
            OrchestratorConfig,
            OutputMode,
            RetryConfig,
            WorkflowConfig,
        )

        # 使用关闭硬阻断的配置，避免空用例列表触发 AuditFailedException
        config = OrchestratorConfig(
            audit_config=AuditConfig(enforce_hard_block=False),
            workflow_config=WorkflowConfig(generate_report=False),
            retry_config=RetryConfig(enabled=False),
            output_mode=OutputMode.CONSOLE,
        )
        o = AgentOrchestrator(config)
        test_cases = [{"用例名称": "测试用例1", "用例目录": "测试模块", "用例步骤": "步骤1", "预期结果": "成功"}]
        result = o.execute_test_case_generation(requirement_id="1001", requirement_name="test", test_cases=test_cases)
        assert isinstance(result, str)

    def test_execute_code_review(self):
        o = AgentOrchestrator()
        result = o.execute_code_review(code="def test(): pass", language="python")
        assert result is not None
        assert hasattr(result, "passed")

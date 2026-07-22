"""WorkflowManager 单元测试"""

from datetime import UTC

import pytest

from modules.trae_test.orchestrator.audit_agent_enhanced import AuditAgent
from modules.trae_test.orchestrator.workflow_manager import (
    StepStatus,
    StepType,
    Workflow,
    WorkflowManager,
    WorkflowStatus,
    WorkflowStep,
)


class TestWorkflowStep:
    def test_init(self):
        step = WorkflowStep(name="test", step_type=StepType.AGENT)
        assert step.name == "test"
        assert step.step_type == StepType.AGENT
        assert step.status == StepStatus.PENDING

    def test_can_execute(self):
        step = WorkflowStep(name="test", depends_on=["dep1"])
        completed = {"dep1": WorkflowStep(status=StepStatus.PASSED)}
        assert step.can_execute(completed) is True

    def test_can_execute_blocked(self):
        step = WorkflowStep(name="test", depends_on=["dep1"])
        completed = {}
        assert step.can_execute(completed) is False

    def test_get_execution_time(self):
        step = WorkflowStep()
        assert step.get_execution_time() == 0.0


class TestWorkflow:
    def test_init(self):
        wf = Workflow(name="test")
        assert wf.name == "test"
        assert wf.steps == []

    def test_add_step(self):
        wf = Workflow(name="test")
        step = WorkflowStep(name="s1")
        wf.add_step(step)
        assert len(wf.steps) == 1

    def test_get_step(self):
        wf = Workflow(name="test")
        step = WorkflowStep(step_id="s1", name="s1")
        wf.add_step(step)
        found = wf.get_step("s1")
        assert found is step

    def test_get_step_nonexistent(self):
        wf = Workflow(name="test")
        assert wf.get_step("nonexistent") is None

    def test_get_execution_time(self):
        wf = Workflow()
        assert wf.get_execution_time() == 0.0

    def test_get_summary(self):
        wf = Workflow(name="test")
        wf.add_step(WorkflowStep(status=StepStatus.PASSED))
        wf.add_step(WorkflowStep(status=StepStatus.FAILED))
        summary = wf.get_summary()
        assert summary["name"] == "test"
        assert summary["passed"] == 1
        assert summary["failed"] == 1


class TestWorkflowManager:
    def test_init(self):
        mgr = WorkflowManager()
        assert mgr.workflows == {}

    def test_create_workflow(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test", description="desc")
        assert wf.name == "test"
        assert wf.description == "desc"
        assert wf.workflow_id in mgr.workflows

    def test_get_workflow(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test")
        found = mgr.get_workflow(wf.workflow_id)
        assert found is wf

    def test_get_workflow_nonexistent(self):
        mgr = WorkflowManager()
        assert mgr.get_workflow("nonexistent") is None

    def test_get_workflow_status(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test")
        status = mgr.get_workflow_status(wf.workflow_id)
        assert status is not None
        assert status["name"] == "test"

    def test_list_workflows(self):
        mgr = WorkflowManager()
        mgr.create_workflow(name="test1")
        mgr.create_workflow(name="test2")
        workflows = mgr.list_workflows()
        assert len(workflows) == 2

    def test_cleanup_completed_workflows(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="test")
        wf.status = WorkflowStatus.COMPLETED
        from datetime import datetime, timedelta

        wf.end_time = datetime.now(UTC) - timedelta(hours=25)
        mgr.cleanup_completed_workflows(max_age_hours=24)
        assert mgr.get_workflow(wf.workflow_id) is None


class TestWorkflowExecution:
    def test_execute_workflow_nonexistent(self):
        mgr = WorkflowManager()
        from modules.trae_test.orchestrator.exception_handler import WorkflowExecutionException

        with pytest.raises(WorkflowExecutionException):
            mgr.execute_workflow("nonexistent", lambda s, d: None, AuditAgent())

    def test_execute_workflow_empty(self):
        mgr = WorkflowManager()
        wf = mgr.create_workflow(name="empty")
        result = mgr.execute_workflow(wf.workflow_id, lambda s, d: None, AuditAgent())
        assert result is wf
        assert result.status == WorkflowStatus.COMPLETED

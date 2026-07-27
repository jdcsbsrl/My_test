from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from modules.trae_test.orchestrator.audit_models import AuditIssue, AuditResult
from modules.trae_test.orchestrator.workflow_state_machine import (
    StateLockManager,
    WorkflowState,
    WorkflowStateMachine,
)


pytestmark = pytest.mark.unit


def make_workflow(state=WorkflowState.PENDING, steps=None):
    return SimpleNamespace(
        workflow_id="wf-1",
        state=state.value,
        steps=steps or [],
        last_state_change=None,
        timeout_count=0,
    )


class TestWorkflowStateMachine:
    def test_transition_updates_state_and_last_change(self):
        machine = WorkflowStateMachine()
        workflow = make_workflow()

        assert machine.transition(workflow, WorkflowState.RUNNING)

        assert workflow.state == WorkflowState.RUNNING.value
        assert isinstance(workflow.last_state_change, datetime)

    def test_invalid_transition_returns_false_without_mutating_state(self):
        machine = WorkflowStateMachine()
        workflow = make_workflow(WorkflowState.PENDING)

        assert not machine.transition(workflow, WorkflowState.COMPLETED)

        assert workflow.state == WorkflowState.PENDING.value
        assert workflow.last_state_change is None

    def test_review_transitions_depend_on_case_status(self):
        machine = WorkflowStateMachine()
        approved = make_workflow(
            WorkflowState.REVIEWING,
            steps=[{"result": [{"审核状态": "APPROVED"}, {"审核状态": "APPROVED"}]}],
        )
        rejected = make_workflow(
            WorkflowState.REVIEWING,
            steps=[SimpleNamespace(result=[{"审核状态": "REJECTED"}])],
        )

        assert machine.can_transition(approved, WorkflowState.AUTO_SOLUTION_GENERATED)
        assert machine.transition(rejected, WorkflowState.GENERATED)
        assert rejected.state == WorkflowState.GENERATED.value

    def test_confirmation_transitions_apply_actions(self):
        machine = WorkflowStateMachine()
        approved = make_workflow(WorkflowState.AWAITING_CONFIRMATION)
        rejected = make_workflow(WorkflowState.AWAITING_CONFIRMATION)

        assert machine.transition(approved, WorkflowState.RUNNING)
        assert approved.confirmation_status == "approved"
        assert isinstance(approved.confirmed_at, datetime)

        assert machine.transition(rejected, WorkflowState.AUTO_SOLUTION_GENERATED)
        assert rejected.confirmation_status == "rejected"

    def test_entering_timeout_state_records_timeout_metadata(self):
        machine = WorkflowStateMachine()
        workflow = make_workflow(WorkflowState.GENERATED)

        assert machine.transition(workflow, WorkflowState.AWAITING_REVIEW)

        assert workflow.timeout_state == WorkflowState.AWAITING_REVIEW.value
        assert isinstance(workflow.timeout_start, datetime)

    def test_check_timeouts_invokes_handler_and_clears_markers(self):
        machine = WorkflowStateMachine()
        workflow = make_workflow(WorkflowState.AWAITING_REVIEW)
        workflow.timeout_state = WorkflowState.AWAITING_REVIEW.value
        workflow.timeout_start = datetime.now() - timedelta(hours=49)
        machine._get_all_workflows = lambda: [workflow]

        machine.check_timeouts()

        assert workflow.timeout_count == 1
        assert not hasattr(workflow, "timeout_state")
        assert not hasattr(workflow, "timeout_start")

    def test_get_available_transitions_filters_by_conditions(self):
        machine = WorkflowStateMachine()
        workflow = make_workflow(WorkflowState.REVIEWING, steps=[{"result": [{"审核状态": "REJECTED"}]}])

        assert machine.get_available_transitions(workflow) == [WorkflowState.GENERATED]

    def test_invalid_workflow_state_defaults_to_pending(self):
        machine = WorkflowStateMachine()
        workflow = SimpleNamespace(workflow_id="wf-1", state="bad", steps=[])

        assert machine.can_transition(workflow, WorkflowState.RUNNING)

    def test_apply_audit_result_passed_advances_review_states(self):
        machine = WorkflowStateMachine()
        result = AuditResult()

        new_state, messages = machine.apply_audit_result(WorkflowState.AWAITING_REVIEW, result)

        assert new_state == WorkflowState.REVIEWING
        assert messages

    def test_apply_audit_result_manual_review_and_error_paths(self):
        machine = WorkflowStateMachine()
        manual = AuditResult(
            issues=[
                AuditIssue(
                    severity="manual_review",
                    rule_id="MANUAL",
                    category="review",
                    message="needs human",
                )
            ]
        )
        manual.passed = False
        failed = AuditResult()
        failed.add_error("ERR", "broken")

        manual_state, manual_messages = machine.apply_audit_result(WorkflowState.REVIEWING, manual)
        failed_state, failed_messages = machine.apply_audit_result(WorkflowState.RUNNING, failed)

        assert manual_state == WorkflowState.AWAITING_REVIEW
        assert "1" in manual_messages[0]
        assert failed_state == WorkflowState.FAILED
        assert "1" in failed_messages[0]


class TestStateLockManager:
    def test_lock_unlock_and_info(self):
        manager = StateLockManager()

        assert manager.lock("wf-1", "review")
        assert not manager.lock("wf-1", "duplicate")
        assert manager.is_locked("wf-1")
        assert manager.get_lock_info("wf-1")["lock_reason"] == "review"
        assert manager.unlock("wf-1")
        assert not manager.unlock("wf-1")

    def test_auto_lock_and_unlock_follow_workflow_state(self):
        manager = StateLockManager()
        workflow = make_workflow(WorkflowState.AWAITING_REVIEW)

        manager.auto_lock_on_review(workflow)
        assert manager.is_locked(workflow.workflow_id)

        workflow.state = WorkflowState.AUTO_SOLUTION_GENERATED.value
        manager.auto_unlock_on_approval(workflow)
        assert not manager.is_locked(workflow.workflow_id)

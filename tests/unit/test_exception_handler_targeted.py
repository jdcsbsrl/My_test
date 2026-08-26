from types import SimpleNamespace

import pytest

from modules.trae_test.orchestrator import exception_handler as exception_handler_module
from modules.trae_test.orchestrator.exception_handler import (
    AgentException,
    AgentNotFoundException,
    AuditFailedException,
    CodeAuditException,
    EnvironmentAuditException,
    ExceptionHandler,
    ExceptionSeverity,
    MaxRetriesExceededException,
    NotificationException,
    SecurityAuditException,
    ValidationException,
    WorkflowExecutionException,
)

pytestmark = pytest.mark.unit


def test_agent_exception_to_dict_and_specialized_details():
    exc = AgentException("base", severity=ExceptionSeverity.LOW, details={"x": 1})

    data = exc.to_dict()

    assert data["type"] == "AgentException"
    assert data["severity"] == "low"
    assert data["details"] == {"x": 1}
    assert exception_handler_module.TestCaseAuditException("bad").severity == ExceptionSeverity.HIGH
    assert CodeAuditException("bad").severity == ExceptionSeverity.HIGH
    assert EnvironmentAuditException("bad").severity == ExceptionSeverity.HIGH
    assert SecurityAuditException("bad").severity == ExceptionSeverity.CRITICAL


def test_context_rich_exception_constructors():
    audit_result = SimpleNamespace(to_dict=lambda: {"passed": False})
    audit = AuditFailedException("audit failed", audit_result=audit_result)
    retries = MaxRetriesExceededException(
        "retry failed", max_retries=2, total_attempts=3, last_exception=ValueError("x")
    )
    workflow = WorkflowExecutionException("workflow failed", workflow_id="wf-1")
    missing = AgentNotFoundException("case-agent")
    validation = ValidationException("invalid", field="name")
    notification = NotificationException("notify", notification_type="email")

    assert audit.details["audit_result"] == {"passed": False}
    assert retries.details["last_exception"] == "x"
    assert workflow.details["workflow_id"] == "wf-1"
    assert missing.details["agent_type"] == "case-agent"
    assert validation.details["field"] == "name"
    assert notification.details["notification_type"] == "email"


def test_handle_agent_exception_notifies_and_records_history():
    messages = []
    handler = ExceptionHandler(notify_callback=messages.append)

    result = handler.handle_exception(SecurityAuditException("secret leak"), context={"step": "audit"})

    assert result["handled"] is True
    assert result["severity"] == "critical"
    assert result["should_notify"] is True
    assert result["should_retry"] is False
    assert messages and "SecurityAuditException" in messages[0]
    assert handler.exception_history[0]["context"] == {"step": "audit"}


def test_handle_generic_exception_and_notification_callback_failure(capsys):
    handler = ExceptionHandler(notify_callback=lambda message: (_ for _ in ()).throw(RuntimeError("boom")))

    result = handler.handle_exception(RuntimeError("plain"))

    assert result["handled"] is True
    assert result["severity"] == "medium"
    assert "boom" in capsys.readouterr().out


def test_should_notify_user_and_retry_matrix():
    handler = ExceptionHandler()
    noisy_audit = SimpleNamespace(errors=[1, 2, 3, 4], to_dict=lambda: {})

    assert handler.should_notify_user(WorkflowExecutionException("wf"))
    assert handler.should_notify_user(MaxRetriesExceededException("max"))
    assert handler.should_notify_user(AuditFailedException("audit", audit_result=noisy_audit))
    assert handler.should_notify_user(AuditFailedException("audit"))
    assert handler.should_retry(AuditFailedException("audit"))
    assert handler.should_retry(EnvironmentAuditException("env"))
    assert not handler.should_retry(ValidationException("bad"))
    assert not handler.should_retry(SecurityAuditException("bad"))


@pytest.mark.parametrize(
    "exception_type",
    [
        exception_handler_module.TestCaseAuditException,
        CodeAuditException,
        EnvironmentAuditException,
        SecurityAuditException,
        AuditFailedException,
        MaxRetriesExceededException,
        WorkflowExecutionException,
        RuntimeError,
    ],
)
def test_generate_recovery_suggestions_for_exception_types(exception_type):
    handler = ExceptionHandler()
    exception = exception_type("problem")

    suggestions = handler.generate_recovery_suggestions(exception)

    assert suggestions


def test_notify_user_history_statistics_and_clear():
    messages = []
    handler = ExceptionHandler(notify_callback=messages.append)
    handler.notify_user("Title", {"a": 1})
    handler.handle_exception(ValidationException("bad field"))
    handler.handle_exception(SecurityAuditException("bad secret"))

    medium_history = handler.get_exception_history(severity=ExceptionSeverity.MEDIUM)
    stats = handler.get_statistics()

    assert "Title" in messages[0]
    assert len(medium_history) == 1
    assert stats["total_exceptions"] == 2
    assert stats["by_type"]["ValidationException"] == 1
    assert stats["by_severity"]["critical"] == 1
    handler.clear_history()
    assert handler.get_statistics()["total_exceptions"] == 0

from types import SimpleNamespace

import pytest

from modules.trae_test.orchestrator import audit_approver as audit_approver_module
from modules.trae_test.orchestrator.audit_approver import AuditApprover
from modules.trae_test.orchestrator.auto_agent import AutoAgent, RiskLevel
from modules.trae_test.orchestrator.config import AuditConfig, OutputMode
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
    TestCaseAuditException as CaseAuditException,
    ValidationException,
    WorkflowExecutionException,
)
from modules.trae_test.orchestrator.monitor import LogLevel, WorkflowMonitor

pytestmark = pytest.mark.unit


KEY_CASE_ID = "\u7528\u4f8b\u7f16\u53f7"
KEY_CASE_NAME = "\u7528\u4f8b\u540d\u79f0"
KEY_STEPS = "\u6d4b\u8bd5\u6b65\u9aa4"


class TestExceptionHandlerTargetedCoverage:
    def test_agent_exception_to_dict_and_specialized_details(self):
        audit_result = SimpleNamespace(to_dict=lambda: {"passed": False, "errors": ["e1"]})
        exceptions = [
            AgentException("base", ExceptionSeverity.LOW, {"k": "v"}),
            CaseAuditException("case", {"case_id": "TC-1"}),
            CodeAuditException("code"),
            EnvironmentAuditException("env"),
            SecurityAuditException("security"),
            AuditFailedException("audit", audit_result=audit_result),
            MaxRetriesExceededException("retry", max_retries=2, total_attempts=3, last_exception=ValueError("bad")),
            WorkflowExecutionException("workflow", workflow_id="wf-1"),
            AgentNotFoundException("AutoAgent"),
            ValidationException("invalid", field="name"),
            NotificationException("notify", notification_type="email"),
        ]

        serialized = [exc.to_dict() for exc in exceptions]

        assert serialized[0]["severity"] == "low"
        assert exceptions[5].details["audit_result"] == {"passed": False, "errors": ["e1"]}
        assert exceptions[6].details["last_exception"] == "bad"
        assert exceptions[7].workflow_id == "wf-1"
        assert exceptions[8].details["agent_type"] == "AutoAgent"
        assert exceptions[9].details["field"] == "name"

    def test_handle_agent_exception_notifies_and_records_history(self):
        notifications = []
        handler = ExceptionHandler(notify_callback=notifications.append)

        result = handler.handle_exception(SecurityAuditException("secret leaked"), context={"workflow": "wf"})

        assert result["handled"] is True
        assert result["severity"] == "critical"
        assert result["should_notify"] is True
        assert result["should_retry"] is False
        assert len(notifications) == 1
        assert "SecurityAuditException" in notifications[0]
        assert handler.exception_history[0]["context"] == {"workflow": "wf"}

    def test_handle_generic_exception_notifies_with_default_recovery(self):
        notifications = []
        handler = ExceptionHandler(notify_callback=notifications.append)

        result = handler.handle_exception(RuntimeError("boom"))

        assert result["severity"] == "medium"
        assert result["should_notify"] is True
        assert result["should_retry"] is False
        assert result["recovery_suggestions"]
        assert "RuntimeError" in notifications[0]

    def test_notify_retry_rules_and_recovery_suggestions(self):
        handler = ExceptionHandler()
        many_errors = SimpleNamespace(errors=[1, 2, 3, 4])
        few_errors = SimpleNamespace(errors=[1, 2, 3])

        assert handler.should_notify_user(AuditFailedException("audit", audit_result=many_errors)) is True
        assert handler.should_notify_user(AuditFailedException("audit", audit_result=few_errors)) is True
        assert handler.should_notify_user(AgentException("low", ExceptionSeverity.LOW)) is False
        assert handler.should_notify_user(MaxRetriesExceededException("max")) is True
        assert handler.should_notify_user(EnvironmentAuditException("env")) is True
        assert handler.should_notify_user(ValidationException("bad")) is False
        assert handler.should_retry(AuditFailedException("audit")) is True
        assert handler.should_retry(EnvironmentAuditException("env")) is True
        assert handler.should_retry(ValidationException("bad")) is False
        assert handler.should_retry(SecurityAuditException("security")) is False
        assert handler.should_retry(RuntimeError("generic")) is True

        exception_types = [
            CaseAuditException("case"),
            CodeAuditException("code"),
            EnvironmentAuditException("env"),
            SecurityAuditException("security"),
            AuditFailedException("audit"),
            MaxRetriesExceededException("max"),
            WorkflowExecutionException("workflow"),
            RuntimeError("generic"),
        ]
        assert all(handler.generate_recovery_suggestions(exc) for exc in exception_types)

    def test_callback_failure_does_not_escape_and_statistics_filter(self, capsys):
        def failing_notify(_message):
            raise RuntimeError("notification down")

        handler = ExceptionHandler(notify_callback=failing_notify)
        handler.handle_exception(SecurityAuditException("critical"))
        handler.handle_exception(ValidationException("validation"))
        handler.handle_exception(RuntimeError("generic"))

        captured = capsys.readouterr()
        high_history = handler.get_exception_history(limit=5, severity=ExceptionSeverity.CRITICAL)
        stats = handler.get_statistics()

        assert "notification down" in captured.out
        assert len(high_history) == 1
        assert stats["total_exceptions"] == 3
        assert stats["by_type"]["SecurityAuditException"] == 1
        assert stats["by_severity"]["critical"] == 1
        handler.clear_history()
        assert handler.get_statistics()["total_exceptions"] == 0

    def test_notify_user_formats_dict_and_plain_payloads(self):
        notifications = []
        handler = ExceptionHandler(notify_callback=notifications.append)

        handler.notify_user("Summary", {"passed": 3, "failed": 1})
        handler.notify_user("Plain", "done")

        assert "passed: 3" in notifications[0]
        assert notifications[1].endswith("done")


class TestAuditApproverTargetedCoverage:
    def test_auto_approve_request_approval_builds_message_and_approves(self, capsys, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        approver = AuditApprover(AuditConfig(interactive_mode=False, auto_approve=True))

        result = approver.request_approval(
            {"action": "generate", "target": "tests/unit/new_test.py", "purpose": "coverage"}
        )
        output = capsys.readouterr().out

        assert result["approved"] is True
        assert approver.user_approved is True
        assert "tests/unit/new_test.py" in output

    def test_non_interactive_without_auto_approve_blocks(self, capsys, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        approver = AuditApprover(AuditConfig(interactive_mode=False, auto_approve=False))

        allowed = approver.prompt_before_operation("generate", "file.py", "unit test")

        assert allowed is False
        assert "[BLOCK]" in capsys.readouterr().out

    def test_ci_environment_disables_interactive_prompt_even_when_configured(self, capsys, monkeypatch):
        monkeypatch.setenv("CI", "true")
        approver = AuditApprover(AuditConfig(interactive_mode=True, auto_approve=False))

        assert approver._prompt_user_approval() is False
        assert approver._is_ci is True
        assert "CI" in capsys.readouterr().out

    def test_interactive_prompt_accepts_yes_empty_and_handles_interrupts(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        approver = AuditApprover(AuditConfig(interactive_mode=True, auto_approve=False))

        monkeypatch.setattr("builtins.input", lambda _prompt: "yes")
        assert approver._prompt_user_approval() is True
        monkeypatch.setattr("builtins.input", lambda _prompt: "")
        assert approver._prompt_user_approval() is True

        def raise_eof(_prompt):
            raise EOFError

        monkeypatch.setattr("builtins.input", raise_eof)
        assert approver._prompt_user_approval() is False

    def test_needs_approval_uses_cached_approval_set(self, monkeypatch):
        calls = {"count": 0}

        class FakeOperationType:
            CODE_GENERATION = "code"
            FOLDER_CREATION = "folder"
            FILE_DELETE = "delete"
            CONFIG_CHANGE = "config"
            READ_ONLY = "read"

            @classmethod
            def from_context(cls, context):
                return context["operation_type"]

        def fake_get_operation_type():
            calls["count"] += 1
            return FakeOperationType

        monkeypatch.setattr(audit_approver_module, "_get_operation_type", fake_get_operation_type)
        approver = AuditApprover(AuditConfig(interactive_mode=False, auto_approve=False))

        assert approver.needs_approval({"operation_type": FakeOperationType.CODE_GENERATION}) is True
        assert approver.needs_approval({"operation_type": FakeOperationType.READ_ONLY}) is False
        assert calls["count"] == 3


class TestAutoAgentAndMonitorAdditionalCoverage:
    def test_auto_agent_high_medium_risks_and_dependencies(self):
        agent = AutoAgent()
        cases = [
            {KEY_CASE_ID: "H", KEY_CASE_NAME: "delete", KEY_STEPS: "\u5220\u9664 \u4fee\u6539 \u6570\u636e\u5e93"},
            {KEY_CASE_ID: "M", KEY_CASE_NAME: "pay", KEY_STEPS: "\u652f\u4ed8 \u91d1\u989d \u7ed3\u7b97"},
            {KEY_CASE_ID: "L", KEY_CASE_NAME: "query", KEY_STEPS: "\u67e5\u8be2 \u67e5\u770b API \u63a5\u53e3"},
        ]

        dependencies = agent._identify_dependencies(cases)
        risk = agent._perform_risk_assessment(cases)

        assert any(dep["mock_required"] for dep in dependencies)
        assert risk["high_risk_count"] == 1
        assert risk["medium_risk_count"] == 1
        assert risk["low_risk_count"] == 0
        assert agent._get_risk_suggestion(RiskLevel.MEDIUM)

    def test_monitor_report_mode_suppresses_console_and_tracks_logs(self, capsys):
        monitor = WorkflowMonitor(output_mode=OutputMode.REPORT)
        monitor.log("silent", LogLevel.WARNING, indent=2)
        monitor.log("error", LogLevel.ERROR)

        assert capsys.readouterr().out == ""
        assert monitor.logs[0]["message"] == "silent"
        assert monitor.get_summary()["warning_count"] == 1

    def test_monitor_plain_console_output_and_progress_bar_boundaries(self, capsys):
        monitor = WorkflowMonitor(output_mode=OutputMode.CONSOLE)
        monitor.enable_colors = False

        monitor.log("plain", LogLevel.DEBUG, indent=1)
        zero = monitor._generate_progress_bar(0, width=4)
        full = monitor._generate_progress_bar(100, width=4)

        output = capsys.readouterr().out
        assert "DEBUG" in output
        assert "plain" in output
        assert zero.startswith("[")
        assert full.endswith("]")

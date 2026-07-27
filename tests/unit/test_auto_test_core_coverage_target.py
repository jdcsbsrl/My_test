import io
import json
import os
import sys
import time
from types import SimpleNamespace

import pytest
import requests

sys.path.insert(0, str((__import__("pathlib").Path(__file__).resolve().parents[2] / "modules")))

from modules.auto_test.core import (
    agent_feedback,
    agent_gc,
    agent_loader,
    agent_phases,
    agent_specialization,
    context_budget,
    env_bootstrap,
    harness_metrics,
    mcp_control_plane,
    pre_audit,
    session_probe,
)
from modules.auto_test.core.driver import HttpDriver
from modules.trae_test.orchestrator.audit_models import AuditIssue, AuditResult


pytestmark = pytest.mark.unit


class TestAgentLoader:
    def test_tier_phase_and_domain_defaults_are_normalized(self):
        entry = {"tier": "1", "phases": ["coding", 3], "domains": ["core", 7]}

        assert agent_loader._tier_of(entry) == 1
        assert agent_loader._tier_of({"tier": "bad"}) == 2
        assert agent_loader._phases_of(entry) == ["coding", "3"]
        assert agent_loader._phases_of({}) == ["initialization", "coding"]
        assert agent_loader._domains_of(entry) == ["core", "7"]
        assert agent_loader._domains_of({}) is None

    def test_recommend_documents_filters_by_phase_domain_sorts_and_deduplicates(self):
        docs = [
            {"path": "late.md", "tier": 3, "phases": ["coding"], "domains": ["sales_api"]},
            {"path": "early.md", "tier": 1, "phases": ["shared"], "domains": ["sales_api"]},
            {"path": "skip-phase.md", "tier": 0, "phases": ["initialization"]},
            {"path": "skip-domain.md", "tier": 0, "phases": ["coding"], "domains": ["sales_ui"]},
            {"path": "early.md", "tier": 9, "phases": ["coding"], "domains": ["sales_api"]},
            {"tier": 1, "phases": ["coding"]},
            "bad",
        ]

        recommended = agent_loader._recommend_documents(docs, "coding", "sales_api")

        assert recommended == ["early.md", "late.md"]

    def test_bootstrap_missing_manifest_returns_safe_summary(self, tmp_path):
        summary = agent_loader.bootstrap_agent_workspace(tmp_path, phase="coding", domain="core")

        assert summary["ok"] is False
        assert summary["documents"] == []
        assert summary["recommended_documents"] == []
        assert summary["phase"] == "coding"
        assert summary["domain"] == "core"
        assert "manifest.json" in summary["error"]

    def test_bootstrap_manifest_reports_missing_and_context_advisory(self, tmp_path, monkeypatch):
        agents_dir = tmp_path / ".agents"
        agents_dir.mkdir()
        (tmp_path / "exists.md").write_text("ok", encoding="utf-8")
        (agents_dir / "progress.json").write_text(
            json.dumps({"schema_version": 1, "features": [{"status": "done"}]}),
            encoding="utf-8",
        )
        (agents_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "version": "1",
                    "documents": [
                        {"path": "exists.md", "tier": "1", "phases": ["coding"], "domains": ["core"]},
                        {"path": "missing.md", "tier": 2, "phases": ["coding"]},
                    ],
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("AGENT_CONTEXT_DEBUG", "1")
        monkeypatch.setenv("CONTEXT_WINDOW_TOKENS", "1")
        monkeypatch.setenv("CONTEXT_BUDGET_MAX_RATIO", "0.1")

        summary = agent_loader.bootstrap_agent_workspace(tmp_path, phase="coding", domain="core")

        assert summary["ok"] is False
        assert summary["missing"] == ["missing.md"]
        assert summary["recommended_documents"] == ["exists.md", "missing.md"]
        assert summary["progress_summary"] == {"feature_count": 1, "by_status": {"done": 1}}
        assert "context_budget" in summary["context_advisory"]


class TestAgentSupportModules:
    def test_resolve_phase_aliases_and_default(self, monkeypatch):
        monkeypatch.setenv("AGENT_PHASE", "plan")
        assert agent_phases.resolve_agent_phase() == "initialization"
        monkeypatch.setenv("AGENT_PHASE", "implementation")
        assert agent_phases.resolve_agent_phase() == "coding"
        monkeypatch.setenv("AGENT_PHASE", "unknown")
        assert agent_phases.resolve_agent_phase() == "coding"

    def test_resolve_domain_aliases_and_filters(self, monkeypatch):
        monkeypatch.setenv("AGENT_DOMAIN", "api")
        assert agent_specialization.resolve_agent_domain() == "sales_api"
        monkeypatch.setenv("AGENT_DOMAIN", "harness")
        assert agent_specialization.resolve_agent_domain() == "core"
        monkeypatch.setenv("AGENT_DOMAIN", "bad")
        assert agent_specialization.resolve_agent_domain() == "full"
        assert agent_specialization.domain_accepts("full", ["sales_ui"])
        assert agent_specialization.domain_accepts("core", None)
        assert not agent_specialization.domain_accepts("sales_api", ["sales_ui"])

    def test_append_auto_failure_record_writes_excerpt_and_hint(self, tmp_path, monkeypatch):
        monkeypatch.setattr(agent_feedback, "repo_root", lambda: tmp_path)
        report = SimpleNamespace(nodeid="tests/test_demo.py::test_x", longrepr="line1\n" + "x" * 500)

        agent_feedback.append_auto_failure_record(report)

        log_text = (tmp_path / ".agents" / "failure_auto_log.md").read_text(encoding="utf-8")
        assert "pytest_fail | tests/test_demo.py::test_x | line1" in log_text
        assert len(log_text.split("|")[-1].strip()) <= 400
        assert "failure_auto_log.md" in os.environ["_AGENT_LAST_FEEDBACK_HINT"]

    def test_context_budget_tracks_over_budget_and_hint(self):
        budget = context_budget.ContextBudget(window_tokens=10, max_ratio=0.4)

        assert budget.record("a", "x" * 20) == 5
        assert budget.estimated_tokens() == 5
        assert budget.current_ratio() == 0.5
        assert budget.is_over_budget()
        assert "exceeds max 40%" in budget.advisory_message()
        assert "pytest" in context_budget.defer_to_dumb_zone("pytest")


class TestAgentGc:
    def test_plan_delete_old_files_ignores_new_files_and_directories(self, tmp_path):
        old_file = tmp_path / "old.log"
        new_file = tmp_path / "new.log"
        old_file.write_text("old", encoding="utf-8")
        new_file.write_text("new", encoding="utf-8")
        (tmp_path / "dir.log").mkdir()
        now = time.time()
        os.utime(old_file, (now - 100, now - 100))
        os.utime(new_file, (now, now))

        plans = agent_gc.plan_delete_old_files(tmp_path, pattern="*.log", max_age_seconds=10, now=now)

        assert [p.path for p in plans] == [old_file]
        assert plans[0].action == "delete_file"
        assert plans[0].bytes_freed == 3

    def test_execute_delete_plans_supports_dry_run_and_ignores_unknown_actions(self, tmp_path):
        target = tmp_path / "old.log"
        target.write_text("12345", encoding="utf-8")
        plans = [
            agent_gc.GcPlan(target, "delete_file", "old", 5),
            agent_gc.GcPlan(tmp_path / "noop", "keep", "manual", 10),
        ]

        assert agent_gc.execute_delete_plans(plans, dry_run=True) == (0, 5)
        assert target.exists()
        assert agent_gc.execute_delete_plans(plans, dry_run=False) == (1, 5)
        assert not target.exists()

    def test_tail_file_in_place_keeps_last_lines_and_backup(self, tmp_path):
        log = tmp_path / "run.log"
        log.write_text("a\nb\nc\nd\n", encoding="utf-8")

        assert agent_gc.tail_file_in_place(log, max_lines=2)

        assert log.read_text(encoding="utf-8") == "c\nd\n"
        assert (tmp_path / "run.log.gc_bak").read_text(encoding="utf-8") == "a\nb\nc\nd\n"
        assert not agent_gc.tail_file_in_place(log, max_lines=2)
        assert not agent_gc.tail_file_in_place(log, max_lines=0)


class TestEnvBootstrapAndMetrics:
    def test_load_dotenv_missing_can_be_optional_or_required(self, tmp_path, monkeypatch):
        monkeypatch.setattr(env_bootstrap, "repo_root", lambda: tmp_path)

        assert env_bootstrap.load_dotenv_from_repo_root(required=False) is None
        with pytest.raises(FileNotFoundError):
            env_bootstrap.load_dotenv_from_repo_root(required=True)

    def test_load_dotenv_from_repo_root_loads_values(self, tmp_path, monkeypatch):
        monkeypatch.setattr(env_bootstrap, "repo_root", lambda: tmp_path)
        (tmp_path / ".env").write_text("TEST_USERNAME=alice\nTEST_PASSWORD=secret\n", encoding="utf-8")
        monkeypatch.delenv("TEST_USERNAME", raising=False)
        monkeypatch.delenv("TEST_PASSWORD", raising=False)

        loaded = env_bootstrap.load_dotenv_from_repo_root(required=True, override=True)

        assert loaded == tmp_path / ".env"
        assert os.getenv("TEST_USERNAME") == "alice"
        assert os.getenv("TEST_PASSWORD") == "secret"
        env_bootstrap.require_plaintext_login_credentials()

    def test_require_plaintext_login_credentials_reports_missing(self, monkeypatch):
        monkeypatch.delenv("TEST_USERNAME", raising=False)
        monkeypatch.delenv("TEST_PASSWORD", raising=False)

        with pytest.raises(RuntimeError) as excinfo:
            env_bootstrap.require_plaintext_login_credentials()

        assert "TEST_USERNAME" in str(excinfo.value)
        assert "TEST_PASSWORD" in str(excinfo.value)

    def test_metrics_recorder_writes_jsonl_and_stream(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HARNESS_METRICS", "yes")
        assert harness_metrics.metrics_enabled()
        path = harness_metrics.default_metrics_path(tmp_path)
        recorder = harness_metrics.HarnessMetricsRecorder(path)

        recorder.session_start(pytest_version="8", cwd=str(tmp_path))
        recorder.test_call_report(nodeid="test_x", outcome="passed", duration=0.1, keywords=["unit"])
        recorder.session_end(exitstatus=0)
        lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        assert [line["type"] for line in lines] == ["session_start", "test_call", "session_end"]
        assert lines[1]["keywords"] == ["unit"]

        stream = io.StringIO()
        recorder.write_event({"type": "custom"}, stream=stream)
        assert json.loads(stream.getvalue()) == {"type": "custom"}


class TestManualGateAndSessionProbe:
    def test_manual_gate_bypasses_when_disabled_or_skipped(self, monkeypatch):
        monkeypatch.delenv("AGENT_MANUAL_GATE", raising=False)
        assert mcp_control_plane.manual_gate("go")
        monkeypatch.setenv("AGENT_MANUAL_GATE", "1")
        monkeypatch.setenv("AGENT_SKIP_MANUAL_GATE", "true")
        assert mcp_control_plane.manual_gate("go")

    def test_manual_gate_auto_approves_non_interactive_stdin(self, monkeypatch):
        monkeypatch.setenv("AGENT_MANUAL_GATE", "1")
        monkeypatch.delenv("AGENT_SKIP_MANUAL_GATE", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(mcp_control_plane.sys.stdin, "isatty", lambda: False)

        assert mcp_control_plane.manual_gate("continue", stream=io.StringIO())

    def test_manual_gate_reads_interactive_stdin_and_handles_oserror(self, monkeypatch):
        class FakeStdin:
            def __init__(self, fail=False):
                self.fail = fail

            def isatty(self):
                return True

            def readline(self):
                if self.fail:
                    raise OSError("closed")
                return "\n"

        monkeypatch.setenv("AGENT_MANUAL_GATE", "1")
        monkeypatch.delenv("AGENT_SKIP_MANUAL_GATE", raising=False)
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setattr(mcp_control_plane.sys, "stdin", FakeStdin())
        assert mcp_control_plane.manual_gate("continue", stream=io.StringIO())
        monkeypatch.setattr(mcp_control_plane.sys, "stdin", FakeStdin(fail=True))
        assert not mcp_control_plane.manual_gate("continue", stream=io.StringIO())

    def test_session_probe_accepts_successful_business_codes(self, monkeypatch):
        class FakeConfig:
            def get(self, key):
                return None

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"code": 200}

        client = SimpleNamespace(get=lambda path, timeout: FakeResponse())
        monkeypatch.setattr(session_probe, "get_config", lambda: FakeConfig())

        session_probe.assert_session_authenticated(client, timeout_sec=1)

    def test_session_probe_tries_custom_path_and_wrapped_user(self, monkeypatch):
        calls = []

        class FakeConfig:
            def get(self, key):
                return "/custom/getInfo"

        class FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"data": {"userId": 1}}

        client = SimpleNamespace(get=lambda path, timeout: calls.append(path) or FakeResponse())
        monkeypatch.setattr(session_probe, "get_config", lambda: FakeConfig())

        session_probe.assert_session_authenticated(client)

        assert calls == ["/custom/getInfo"]

    def test_session_probe_skips_unauthorized_not_found_and_request_errors(self, monkeypatch):
        class FakeConfig:
            def get(self, key):
                return None

        class FakeResponse:
            def __init__(self, status_code, body=None):
                self.status_code = status_code
                self._body = body or {}

            def raise_for_status(self):
                return None

            def json(self):
                return self._body

        responses = [
            FakeResponse(401),
            FakeResponse(404),
            requests.RequestException("down"),
            FakeResponse(200, {"code": 401}),
        ]

        def fake_get(path, timeout):
            item = responses.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

        client = SimpleNamespace(get=fake_get)
        monkeypatch.setattr(session_probe, "get_config", lambda: FakeConfig())

        with pytest.raises(AssertionError) as excinfo:
            session_probe.assert_session_authenticated(client)

        assert "getInfo" in str(excinfo.value)


class TestHttpDriverCore:
    def test_driver_uses_config_and_builds_urls(self):
        config = SimpleNamespace(get=lambda key, default=None: {"api.verify_ssl": False, "api.timeout": 7}.get(key, default))
        driver = HttpDriver("https://example.test", config)

        assert driver.timeout == 7
        assert driver._verify_ssl is False
        assert driver._build_url("/api") == "https://example.test/api"
        assert driver._build_url("https://other.test/x") == "https://other.test/x"
        assert driver._build_url("relative") == "relative"

    def test_driver_request_delegates_to_session_and_close(self):
        calls = {}

        class FakeSession:
            def request(self, **kwargs):
                calls["request"] = kwargs
                return SimpleNamespace(status_code=204)

            def close(self):
                calls["closed"] = True

        driver = HttpDriver("https://example.test")
        driver._session = FakeSession()
        driver.timeout = 3
        driver._verify_ssl = False

        response = driver.post("/items", json={"x": 1})
        driver.close()

        assert response.status_code == 204
        assert calls["request"]["method"] == "POST"
        assert calls["request"]["url"] == "https://example.test/items"
        assert calls["request"]["timeout"] == 3
        assert calls["request"]["verify"] is False
        assert calls["request"]["json"] == {"x": 1}
        assert calls["closed"] is True

    def test_driver_handle_response_falls_back_to_text(self):
        response = SimpleNamespace(json=lambda: (_ for _ in ()).throw(ValueError()), text="plain", status_code=500)
        driver = HttpDriver("")

        assert driver._handle_response(response) == {"text": "plain", "status_code": 500}


class TestPreAudit:
    def test_check_environment_delegates_to_gateway_with_blocking_context(self):
        calls = []
        result = AuditResult()
        audit = pre_audit.PreAudit()
        audit.gateway = SimpleNamespace(audit=lambda payload, kind, context: calls.append((payload, kind, context)) or result)

        assert audit.check_environment({"env": "uat"}) is result

        assert calls == [
            (
                {"env": "uat"},
                "environment",
                {"source": "auto_test_pre_audit", "block_on_fail": True},
            )
        ]

    def test_check_test_readiness_reports_missing_fields_and_empty_cases(self):
        audit = pre_audit.PreAudit()

        result = audit.check_test_readiness({"test_data": {}, "test_cases": []})

        rule_ids = {issue.rule_id for issue in result.issues}
        assert "READINESS_MISSING_TEST_ACCOUNT" in rule_ids
        assert "READINESS_NO_TEST_CASES" in rule_ids
        assert result.passed

    def test_check_test_readiness_delegates_non_dict_plans(self):
        calls = []
        result = AuditResult()
        audit = pre_audit.PreAudit()
        audit.gateway = SimpleNamespace(audit=lambda payload, kind, context: calls.append((payload, kind, context)) or result)

        assert audit.check_test_readiness(["case"]) is result

        assert calls == [
            (
                ["case"],
                "test_case",
                {"source": "auto_test_pre_audit", "block_on_fail": False},
            )
        ]

    def test_pre_audit_blocks_failed_environment_and_allows_warning_readiness(self, caplog):
        failed = AuditResult()
        failed.issues.append(AuditIssue("error", "ENV_FAIL", "env", "bad env"))
        warning = AuditResult()
        warning.issues.append(AuditIssue("warning", "WARN", "readiness", "missing"))
        audit = pre_audit.PreAudit()
        audit.check_environment = lambda env: failed

        assert not audit.pre_audit({"env": "prod"})

        audit.check_environment = lambda env: AuditResult()
        audit.check_test_readiness = lambda plan: warning
        assert audit.pre_audit({"env": "uat"}, {"test_cases": ["case"]})

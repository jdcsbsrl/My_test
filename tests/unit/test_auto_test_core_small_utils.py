import io
import json

import pytest

from modules.auto_test.core.agent_phases import (
    PHASE_CODING,
    PHASE_INITIALIZATION,
    resolve_agent_phase,
)
from modules.auto_test.core.context_budget import ContextBudget, _estimate_tokens, defer_to_dumb_zone
from modules.auto_test.core.harness_metrics import (
    HarnessMetricsRecorder,
    default_metrics_path,
    metrics_enabled,
)

pytestmark = pytest.mark.unit


class TestContextBudget:
    def test_estimate_tokens_handles_empty_and_short_text(self):
        assert _estimate_tokens("") == 0
        assert _estimate_tokens("abc") == 1
        assert _estimate_tokens("abcdefgh") == 2

    def test_record_ratio_and_budget_message(self):
        budget = ContextBudget(window_tokens=100, max_ratio=0.2)

        assert budget.record("prompt", "x" * 120) == 30
        assert budget.estimated_tokens() == 30
        assert budget.current_ratio() == 0.3
        assert budget.is_over_budget()
        assert "exceeds max 20%" in budget.advisory_message()

    def test_under_budget_and_invalid_window_do_not_warn(self):
        budget = ContextBudget(window_tokens=0, max_ratio=0.1)
        budget.record("prompt", "x" * 100)

        assert budget.current_ratio() == 0.0
        assert not budget.is_over_budget()
        assert budget.advisory_message() is None

    def test_environment_defaults_are_respected(self, monkeypatch):
        monkeypatch.setenv("CONTEXT_WINDOW_TOKENS", "200")
        monkeypatch.setenv("CONTEXT_BUDGET_MAX_RATIO", "0.5")

        budget = ContextBudget()

        assert budget.window_tokens == 200
        assert budget.max_ratio == 0.5

    def test_defer_to_dumb_zone_formats_reason(self):
        assert "run pytest" in defer_to_dumb_zone("large fixture")
        assert "large fixture" in defer_to_dumb_zone("large fixture")


class TestHarnessMetrics:
    @pytest.mark.parametrize("value", ["1", "true", "yes", "TRUE"])
    def test_metrics_enabled_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("HARNESS_METRICS", value)

        assert metrics_enabled()

    def test_metrics_enabled_false_by_default(self, monkeypatch):
        monkeypatch.delenv("HARNESS_METRICS", raising=False)

        assert not metrics_enabled()

    def test_default_metrics_path(self, tmp_path):
        assert default_metrics_path(tmp_path) == tmp_path / ".runtime" / "reports" / "harness_metrics" / "events.jsonl"

    def test_recorder_writes_to_stream_and_file(self, tmp_path):
        recorder = HarnessMetricsRecorder(tmp_path / "events.jsonl")
        recorder._started = 1.0
        stream = io.StringIO()

        recorder.write_event({"type": "custom", "value": 1}, stream=stream)
        recorder.session_start(pytest_version="8", cwd="repo")
        recorder.test_call_report(nodeid="test_x", outcome="passed", duration=0.1, keywords=["unit"])
        recorder.session_end(exitstatus=0)

        assert json.loads(stream.getvalue()) == {"type": "custom", "value": 1}
        lines = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()]
        assert lines[0]["type"] == "session_start"
        assert lines[0]["pytest_version"] == "8"
        assert isinstance(lines[0]["ts"], float)
        assert lines[1]["type"] == "test_call"
        assert lines[1]["keywords"] == ["unit"]
        assert lines[2]["type"] == "session_end"
        assert lines[2]["wall_sec"] > 0


class TestAgentPhases:
    @pytest.mark.parametrize("value", ["init", "initialization", "plan", "planning"])
    def test_initialization_aliases(self, monkeypatch, value):
        monkeypatch.setenv("AGENT_PHASE", value)

        assert resolve_agent_phase() == PHASE_INITIALIZATION

    @pytest.mark.parametrize("value", ["code", "coding", "implement", "implementation", "unknown"])
    def test_coding_aliases_and_unknown_default(self, monkeypatch, value):
        monkeypatch.setenv("AGENT_PHASE", value)

        assert resolve_agent_phase() == PHASE_CODING

    def test_default_phase_is_coding(self, monkeypatch):
        monkeypatch.delenv("AGENT_PHASE", raising=False)

        assert resolve_agent_phase() == PHASE_CODING

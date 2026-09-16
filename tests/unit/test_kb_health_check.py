"""Unit tests for the read-only knowledge-base health gate."""

from __future__ import annotations

import json
from pathlib import Path

import tools.kb_health_check as health_check


class FakeManager:
    def __init__(self, health: dict, dedupe: dict | None = None) -> None:
        self.health_result = health
        self.dedupe_result = dedupe or {"success": True, "read_only": True, "summary": {}}
        self.dedupe_calls = 0

    def health_check(self) -> dict:
        return self.health_result

    def dedupe_report(self) -> dict:
        self.dedupe_calls += 1
        return self.dedupe_result


def healthy_result() -> dict:
    return {
        "success": True,
        "read_only": True,
        "registered_file_count": 67,
        "scan": {"needs_processing": [], "errors": []},
        "index_status": {"valid": True, "missing_files": [], "stale_files": []},
        "errors": [],
    }


def test_healthy_gate_returns_zero_without_dedupe() -> None:
    manager = FakeManager(healthy_result())

    report, exit_code = health_check.run_check(manager)

    assert exit_code == health_check.EXIT_HEALTHY
    assert report["status"] == "healthy"
    assert report["read_only"] is True
    assert report["dedupe"] is None
    assert manager.dedupe_calls == 0


def test_warning_gate_reports_pending_files_and_duplicate_candidates() -> None:
    manager = FakeManager(
        {
            **healthy_result(),
            "scan": {"needs_processing": [{"file": "new.json"}], "errors": []},
        },
        {
            "success": True,
            "read_only": True,
            "summary": {
                "normalized_title_duplicate_count": 1,
                "cross_file_rule_id_duplicate_count": 0,
                "exact_content_duplicate_count": 0,
                "similarity_candidate_count": 2,
            },
        },
    )

    report, exit_code = health_check.run_check(manager, include_dedupe=True)

    assert exit_code == health_check.EXIT_WARNING
    assert report["status"] == "warning"
    assert manager.dedupe_calls == 1
    assert any("待处理知识文件" in warning for warning in report["warnings"])
    assert any("规范化标题重复" in warning for warning in report["warnings"])


def test_blocking_gate_maps_health_failure_to_exit_two() -> None:
    manager = FakeManager(
        {
            "success": False,
            "read_only": True,
            "scan": {"needs_processing": [], "errors": []},
            "index_status": {"valid": False},
            "errors": [{"component": "global_index", "error": "mismatch"}],
        }
    )

    report, exit_code = health_check.run_check(manager)

    assert exit_code == health_check.EXIT_BLOCKING
    assert report["status"] == "blocking"
    assert report["errors"][0]["component"] == "global_index"


def test_non_read_only_component_is_blocking() -> None:
    manager = FakeManager({**healthy_result(), "read_only": False})

    report, exit_code = health_check.run_check(manager)

    assert exit_code == health_check.EXIT_BLOCKING
    assert "read-only report" in report["errors"][0]


def test_dedupe_failure_is_blocking_and_does_not_expose_rule_content() -> None:
    manager = FakeManager(
        healthy_result(),
        {
            "success": False,
            "read_only": True,
            "unreadable_files": [{"file_id": "secret", "error": "unreadable"}],
            "summary": {},
            "content": "must not be copied",
        },
    )

    report, exit_code = health_check.run_check(manager, include_dedupe=True)

    assert exit_code == health_check.EXIT_BLOCKING
    assert report["status"] == "blocking"
    assert "must not be copied" not in json.dumps(report, ensure_ascii=False)


def test_write_report_uses_runtime_report_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(health_check, "runtime_dir", lambda kind: tmp_path)
    report, exit_code = health_check.run_check(FakeManager(healthy_result()), persist_report=True)

    assert exit_code == health_check.EXIT_HEALTHY
    report_path = Path(report["report_path"])
    assert report_path.parent == tmp_path / "knowledge_base"
    persisted = json.loads(report_path.read_text(encoding="utf-8"))
    assert persisted["read_only"] is True
    assert persisted["status"] == "healthy"


def test_report_write_failure_is_blocking() -> None:
    def failing_writer(report: dict) -> Path:
        raise OSError("report directory unavailable")

    report, exit_code = health_check.run_check(
        FakeManager(healthy_result()),
        persist_report=True,
        report_writer=failing_writer,
    )

    assert exit_code == health_check.EXIT_BLOCKING
    assert report["status"] == "blocking"
    assert report["errors"][0]["component"] == "report_writer"


def test_main_returns_exit_code_and_supports_mock_manager(monkeypatch, capsys) -> None:
    manager = FakeManager(healthy_result())
    monkeypatch.setattr(health_check, "KnowledgeBaseManager", lambda: manager)

    exit_code = health_check.main(["--include-dedupe"], manager_factory=lambda: manager)

    output = json.loads(capsys.readouterr().out)
    assert exit_code == health_check.EXIT_HEALTHY
    assert output["summary"]["dedupe_checked"] is True

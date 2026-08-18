from pathlib import Path

from tools.report_generator import TestReportGenerator as ReportGenerator
from tools.multi_agent_runner import create_orchestrator
import tools.auto_login as auto_login


def test_html_report_escapes_user_supplied_result_text():
    report = ReportGenerator()
    report.add_test_result("<script>alert(1)</script>", "FAIL", "<img src=x onerror=alert(1)>")

    html = report.generate_html_report()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_db_cli_does_not_embed_database_credentials():
    source = Path("tools/db_redis_cli.py").read_text(encoding="utf-8")

    assert "postgresql://postgres:" not in source
    assert "DATABASE_URL" not in source or "os.environ[\"DATABASE_URL\"]" not in source


def test_project_auditor_root_is_derived_from_file_location():
    source = Path("tools/project_structure_auditor.py").read_text(encoding="utf-8")

    assert 'D:\\Working\\test_erp' not in source
    assert "Path(__file__).resolve().parent.parent" in source


def test_knowledge_base_cli_uses_process_exit_status():
    source = Path("tools/kb_manager.py").read_text(encoding="utf-8")

    assert "raise SystemExit(main())" in source
    assert "exit_code = 0 if result.get(\"success\", False) else 1" in source


def test_database_migration_requires_exactly_one_migration_scope():
    source = Path("tools/db_migrate_cli.py").read_text(encoding="utf-8")

    assert "add_mutually_exclusive_group(required=True)" in source


def test_auto_login_returns_failure_status_when_any_environment_fails(monkeypatch):
    monkeypatch.setattr(auto_login, "login_to_env", lambda env, force=False: {"env": env, "success": env == "test"})
    monkeypatch.setattr("sys.argv", ["auto_login.py", "--env", "all"])

    assert auto_login.main() == 1


def test_code_review_does_not_run_environment_audit(capsys):
    orchestrator = create_orchestrator()

    result = orchestrator.execute_code_review("def hello():\n    return 1")

    assert result.passed is True
    workflow = list(orchestrator.workflow_manager.workflows.values())[-1]
    assert [step.audit_type.value for step in workflow.steps] == ["code", "security"]

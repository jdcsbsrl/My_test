"""CI wiring contract for weekly business report requirement 1003838."""

from pathlib import Path

import yaml


def test_weekly_report_regression_is_wired_to_admin_and_role_ci_lanes() -> None:
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
    workflow = yaml.load(workflow_path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    admin_job = workflow["jobs"]["sales-ui-tests"]
    admin_job_env = admin_job["env"]
    admin_files = [entry["test_files"] for entry in admin_job["strategy"]["matrix"]["include"]]
    weekly_admin_shard = next(entry for entry in admin_files if "test_weekly_business_report_1003838.py" in entry)
    assert "-m 'not slow'" in weekly_admin_shard
    assert admin_job_env["TEST_ENV"] == "test"
    assert admin_job_env["WEEKLY_REPORT_ROLE"] == "admin"

    role_job = workflow["jobs"]["weekly-report-role-regression"]
    assert role_job["needs"] == "code-quality"
    role_values = [entry["role"] for entry in role_job["strategy"]["matrix"]["include"]]
    assert role_values == ["manager", "sales"]
    role_steps = {step.get("name"): step for step in role_job["steps"] if step.get("name")}
    command = role_steps["Run read-only weekly-report role checks"]["run"]
    assert "WEEKLY_REPORT_ROLE" in command
    assert "test_work_plan_selector_is_scoped_to_the_configured_role" in command

    assert "weekly-report-role-regression" in workflow["jobs"]["report"]["needs"]
    assert "weekly-report-role-regression" in workflow["jobs"]["collect-failure-logs"]["needs"]

    manual_source_job = workflow["jobs"]["weekly-report-source-audit"]
    assert "workflow_dispatch" in manual_source_job["if"]
    assert "inputs.run_weekly_report_source_audit" in manual_source_job["if"]
    assert manual_source_job["env"]["TEST_ENV"] == "test"
    assert any(
        "test_latest_week_admin_reports_match_source_receivable_bills" in step.get("run", "")
        for step in manual_source_job["steps"]
    )
    assert "weekly-report-source-audit" in workflow["jobs"]["report"]["needs"]
    assert "weekly-report-source-audit" in workflow["jobs"]["collect-failure-logs"]["needs"]

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "ci-cd.yml"
REQUIREMENT_TEST = "modules/auto_test/tests/test_export_requirement_1003531.py"


def _sales_job() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    return workflow.split("  sales-ui-tests:", maxsplit=1)[1].split("  inventory-tests:", maxsplit=1)[0]


def test_requirement_1003531_fast_regression_uses_admin_test_lane() -> None:
    sales_job = _sales_job()

    assert "TEST_ENV: test" in sales_job
    assert "TEST_USERNAME: ${{ secrets.ADMIN_USERNAME }}" in sales_job
    assert "TEST_PASSWORD: ${{ secrets.ADMIN_PASSWORD }}" in sales_job
    assert "shard: 14" in sales_job
    assert f"{REQUIREMENT_TEST} -m 'not slow'" in sales_job


def test_requirement_1003531_timer_dependent_cases_stay_out_of_ci() -> None:
    sales_job = _sales_job()

    assert f"{REQUIREMENT_TEST} -m 'not slow'" in sales_job
    assert f"{REQUIREMENT_TEST} -m slow" not in sales_job

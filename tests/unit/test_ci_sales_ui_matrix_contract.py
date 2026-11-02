"""Contracts for requirement 1003845 in the administrator sales UI matrix."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "ci-cd.yml"
REQUIREMENT_TEST = "modules/auto_test/tests/test_sales_order_fixed_category_1003845.py"


def test_requirement_1003845_has_dedicated_administrator_sales_shard() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    sales_job = workflow.split("  sales-ui-tests:", maxsplit=1)[1].split("  inventory-tests:", maxsplit=1)[0]

    assert "- shard: 13" in sales_job
    assert f'test_files: "{REQUIREMENT_TEST}"' in sales_job
    assert sales_job.count(REQUIREMENT_TEST) == 1
    assert "TEST_USERNAME: ${{ secrets.ADMIN_USERNAME }}" in sales_job
    assert "TEST_PASSWORD: ${{ secrets.ADMIN_PASSWORD }}" in sales_job


def test_requirement_1003845_is_not_in_group_leader_inventory_matrix() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    inventory_job = workflow.split("  inventory-tests:", maxsplit=1)[1].split("\n  report:", maxsplit=1)[0]

    assert REQUIREMENT_TEST not in inventory_job

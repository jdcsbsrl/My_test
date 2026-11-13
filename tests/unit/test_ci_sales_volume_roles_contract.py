"""Protect the CI role matrix for the merged sales volume report."""

from pathlib import Path

import yaml


def test_sales_volume_role_matrix_and_full_regression_are_wired() -> None:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["sales-volume-roles"]
    roles = {
        entry["role"]: (entry["username_secret"], entry["password_secret"])
        for entry in job["strategy"]["matrix"]["include"]
    }
    assert roles == {
        "admin": ("ADMIN_USERNAME", "ADMIN_PASSWORD"),
        "manager": ("LEADER_USERNAME", "LEADER_PASSWORD"),
        "sales": ("SALES_USERNAME", "SALES_PASSWORD"),
        "assistant": ("ASSISTANT_USERNAME", "ASSISTANT_PASSWORD"),
        "procurement": ("PROCUREMENT_USERNAME", "PROCUREMENT_PASSWORD"),
    }
    assert job["env"]["SALES_VOLUME_ROLE"] == "${{ matrix.role }}"
    assert job["env"]["TEST_USERNAME"] == "${{ secrets[matrix.username_secret] }}"
    assert job["env"]["TEST_PASSWORD"] == "${{ secrets[matrix.password_secret] }}"
    steps = {step.get("name"): step for step in job["steps"] if step.get("name")}
    assert "-m 'not slow'" in steps["Run role permissions regression"]["run"]
    full = steps["Run full sorting and export regression"]
    assert "inputs.sales_volume_full" not in full.get("if", "")
    assert "test_multistore_sku_sales_against_order_items" in steps["Run role search and source-data regression"]["run"]
    assert "test_procurement_source_data" in steps["Run procurement source reconciliation"]["run"]
    for expected in (
        "sort_regression.py",
        "-k async_export",
        "test_role_denied_store",
        "test_procurement_data_matches_administrator",
    ):
        assert expected in full["run"]
    assert "sales-volume-roles" in workflow["jobs"]["report"]["needs"]

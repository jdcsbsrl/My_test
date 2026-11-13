from pathlib import Path

import yaml


def test_sales_volume_uses_one_administrator_shard_and_one_multi_role_job() -> None:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["sales-volume-roles"]
    assert "strategy" not in job
    env = job["env"]
    for role in ("LEADER", "SALES", "ASSISTANT", "PROCUREMENT"):
        for field in ("USERNAME", "PASSWORD"):
            name = f"{role}_{field}"
            assert env[name] == "${{ secrets." + name + " }}"
    steps = {step.get("name"): step for step in job["steps"] if step.get("name")}
    script = steps["Run each role independently"]["run"]
    assert "for role in manager sales assistant procurement" in script
    assert 'export SALES_VOLUME_ROLE="$role"' in script
    assert "--basetemp" in script and "${SALES_VOLUME_ROLE}-${counter}" in script
    assert "overall=1" in script and 'exit "$overall"' in script
    for expected in (
        "test_multistore_sku_sales_against_order_items",
        "test_procurement_source_data",
        "test_role_denied_store",
        "test_procurement_data_matches_administrator",
        "sort_regression.py",
        "-k async_export",
    ):
        assert expected in script
    scan = steps["Scan role test artifacts for secrets"]["run"]
    assert "for role in admin manager sales assistant procurement" in scan
    assert "sales-volume-roles" in workflow["jobs"]["report"]["needs"]
    admin_steps = {step.get("name"): step for step in workflow["jobs"]["sales-ui-tests"]["steps"] if step.get("name")}
    admin_slow = admin_steps["Run administrator sales volume slow regression"]
    assert "matrix.shard == 10" in admin_slow["if"]
    assert "test_sales_volume_regression.py" in admin_slow["run"]
    assert "test_sales_volume_sort_regression.py" in admin_slow["run"]
    assert "-m slow" in admin_slow["run"]

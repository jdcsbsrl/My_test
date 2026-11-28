from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci-cd.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW_PATH.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_requirement_1004021_is_on_group_leader_ci_shard() -> None:
    workflow = _workflow()
    inventory_job = workflow["jobs"]["inventory-tests"]

    assert inventory_job["env"]["TEST_USERNAME"] == "${{ secrets.LEADER_USERNAME }}"
    assert inventory_job["env"]["TEST_PASSWORD"] == "${{ secrets.LEADER_PASSWORD }}"
    assert any(
        entry["shard"] == "10" and "test_inventory_sync_requirement_1004021.py" in entry["test_files"]
        for entry in inventory_job["strategy"]["matrix"]["include"]
    )


def test_order_matrix_preflight_always_runs_on_shard_10_and_uses_order_number_secret() -> None:
    workflow = _workflow()
    dispatch_inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    inventory_steps = workflow["jobs"]["inventory-tests"]["steps"]
    preflight = next(
        step for step in inventory_steps if step.get("name") == "Run inventory sync 1004021 order matrix preflight"
    )

    assert "run_inventory_sync_1004021_order_matrix" not in dispatch_inputs
    assert preflight["if"] == "${{ always() && matrix.shard == 10 && !cancelled() }}"
    assert preflight["env"]["INVENTORY_SYNC_ORDER_NUMBERS"] == "${{ secrets.INVENTORY_SYNC_ORDER_NUMBERS }}"
    assert "test_inventory_sync_order_matrix_1004021.py" in preflight["run"]

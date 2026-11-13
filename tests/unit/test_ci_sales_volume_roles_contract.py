from pathlib import Path

import yaml

from modules.auto_test.tests.test_sales_volume_regression import (
    _dimension_filter_store_scope,
    _normalize_store_name,
    _store_picker_group_names,
)


def test_sales_volume_uses_two_balanced_parallel_lanes() -> None:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["sales-volume-regression"]
    assert job["timeout-minutes"] == "120"
    assert job["strategy"]["max-parallel"] == "2"
    assert [entry["lane"] for entry in job["strategy"]["matrix"]["include"]] == ["A", "B"]
    env = job["env"]
    for role in ("ADMIN", "LEADER", "SALES", "ASSISTANT", "PROCUREMENT"):
        for field in ("USERNAME", "PASSWORD"):
            name = f"{role}_{field}"
            assert env[name] == "${{ secrets." + name + " }}"
    steps = {step.get("name"): step for step in job["steps"] if step.get("name")}
    script = steps["Run assigned roles independently"]["run"]
    assert "A) roles=(admin sales)" in script
    assert "B) roles=(manager assistant procurement)" in script
    assert 'for role in "${roles[@]}"' in script
    assert "run_phase 完整主回归" in script and "run_phase 慢速排序与导出" in script
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
        "test_dimension_specific_filter",
    ):
        assert expected in script
    scan = steps["Scan role test artifacts for secrets"]["run"]
    assert "for role in admin manager sales assistant procurement" in scan
    assert "sales-volume-regression" in workflow["jobs"]["report"]["needs"]
    assert "sales-volume-regression" in workflow["jobs"]["collect-failure-logs"]["needs"]
    ui_matrix = workflow["jobs"]["sales-ui-tests"]["strategy"]["matrix"]["include"]
    assert all(entry["shard"] != "10" for entry in ui_matrix)


def test_procurement_dimension_filters_do_not_require_store_permissions() -> None:
    def missing_store_scope():
        raise AssertionError("采购筛选不应读取受店铺权限约束的样本")

    assert _dimension_filter_store_scope("procurement", missing_store_scope) == []
    assert _dimension_filter_store_scope("manager", lambda: ["store-1", "store-2"]) == ["store-1", "store-2"]


def test_store_picker_groups_are_discovered_from_the_visible_summary() -> None:
    summary = "清除已选\n显示已停用店铺\nShopify\n(61)\nOther\n(5)\nWhop\n(2)\n全部Shopify店铺"

    assert _store_picker_group_names(summary) == ["Shopify", "Other", "Whop"]
    assert _normalize_store_name(" Whop\u200b Test Store ") == "whopteststore"

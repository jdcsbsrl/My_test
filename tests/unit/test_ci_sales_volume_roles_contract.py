from pathlib import Path

import pytest
import yaml

from modules.auto_test.tests.test_sales_volume_regression import (
    _dimension_filter_store_scope,
    _normalize_store_name,
    _store_picker_group_names,
)
from modules.auto_test.tests.test_sales_volume_role_regression import _procurement_async_export_payload


def test_sales_volume_uses_two_balanced_parallel_lanes() -> None:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["sales-volume-regression"]
    window_job = workflow["jobs"]["sales-volume-window"]
    assert job["timeout-minutes"] == "120"
    assert job["strategy"]["max-parallel"] == "2"
    assert [entry["lane"] for entry in job["strategy"]["matrix"]["include"]] == ["A", "B"]
    assert job["needs"] == ["code-quality", "sales-volume-window"]
    assert job["env"]["SALES_VOLUME_AS_OF_DATE"] == "${{ needs.sales-volume-window.outputs.as_of_date }}"
    assert window_job["outputs"]["as_of_date"] == "${{ steps.anchor.outputs.as_of_date }}"
    assert "TZ=Asia/Shanghai date +%F" in window_job["steps"][0]["run"]
    env = job["env"]
    for role in ("ADMIN", "LEADER", "SALES", "ASSISTANT", "PROCUREMENT"):
        for field in ("USERNAME", "PASSWORD"):
            name = f"{role}_{field}"
            assert env[name] == "${{ secrets." + name + " }}"
    steps = {step.get("name"): step for step in job["steps"] if step.get("name")}
    script = steps["Run assigned roles independently"]["run"]
    assert "A) roles=(admin sales procurement)" in script
    assert "B) roles=(manager assistant)" in script
    assert 'for role in "${roles[@]}"' in script
    assert "run_phase 完整主回归" in script and "run_phase 慢速排序与导出" in script
    assert 'export SALES_VOLUME_ROLE="$role"' in script
    assert "--basetemp" in script and "${SALES_VOLUME_ROLE}-${counter}" in script
    assert "overall=1" in script and 'exit "$overall"' in script
    for expected in (
        "test_multistore_sku_sales_against_order_items",
        "test_procurement_source_data",
        "test_procurement_async_export_matches_query",
        "test_role_denied_store",
        "test_procurement_data_matches_administrator",
        "sort_regression.py",
        "-k async_export",
        "run_phase 采购异步导出",
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


def test_procurement_async_export_uses_no_store_filter():
    payload = _procurement_async_export_payload(
        report_query=lambda endpoint, values: pytest.fail("Non-category sampling should not query categories"),
        report_window=("2026-10-15 00:00:00", "2026-11-13 23:59:59"),
        dimension="warehouse",
    )

    assert payload["storeIds"] == []


def test_procurement_category_export_selects_a_detail_sample_under_limit():
    def report_query(endpoint, payload):
        if endpoint == "queryCategorySalesDimensionReport":
            class_id = "small" if payload["payTimeBegin"] == "2026-11-07 00:00:00" else "large"
            return {"code": 200, "total": 1, "rows": [{"classId": class_id}]}
        if endpoint == "queryCategorySalesDimensionExpand":
            count = 1 if payload["classIds"] == ["small"] else 20001
            return {"code": 200, "data": [None] * count}
        pytest.fail(f"Unexpected report endpoint: {endpoint}")

    payload = _procurement_async_export_payload(
        report_query,
        ("2026-10-15 00:00:00", "2026-11-13 23:59:59"),
        "category",
    )

    assert payload["classIds"] == ["small"]
    assert payload["payTimeBegin"] == "2026-11-07 00:00:00"
    assert payload["storeIds"] == []


def test_procurement_source_reconciliation_calls_shared_assertions(monkeypatch):
    from modules.auto_test.tests import test_sales_volume_regression as report_tests
    from modules.auto_test.tests import test_sales_volume_role_regression as role_tests

    administrator_client = object()
    report_query = object()
    orders = [{"orderNo": "order-1"}]
    details = {"order-1": [{"itemId": "SKU-1", "quantity": 1}]}
    calls = {}

    monkeypatch.setattr(report_tests, "_fetch_order_data", lambda *args, **kwargs: (orders, details))
    monkeypatch.setattr(
        report_tests,
        "_assert_sku_sales_match_order_source",
        lambda *args: calls.setdefault("sales", args),
    )
    monkeypatch.setattr(
        report_tests,
        "_assert_inventory_matches_report",
        lambda *args: calls.setdefault("inventory", args),
    )

    role_tests.test_procurement_source_data(
        administrator_client,
        "https://test.invalid",
        report_query,
        ("2026-11-13 00:00:00", "2026-11-13 23:59:59"),
        "procurement",
    )

    window = ("2026-11-13 00:00:00", "2026-11-13 23:59:59")
    assert calls["sales"] == (report_query, window, [], orders, details, administrator_client, "https://test.invalid")
    assert calls["inventory"] == (
        administrator_client,
        "https://test.invalid",
        report_query,
        window,
        [],
    )

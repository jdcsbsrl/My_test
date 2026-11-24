from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml

from modules.auto_test.tests.test_sales_volume_regression import (
    _fetch_export_task_page,
    _report_auth_failure_diagnostic,
    _dimension_filter_store_scope,
    _normalize_store_name,
    _store_picker_group_names,
)
from modules.auto_test.tests.test_sales_volume_role_regression import _procurement_async_export_payload


def test_sales_volume_uses_three_bounded_parallel_lanes() -> None:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci-cd.yml"
    workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["sales-volume-regression"]
    window_job = workflow["jobs"]["sales-volume-window"]
    assert job["timeout-minutes"] == "110"
    assert job["strategy"]["max-parallel"] == "3"
    assert [entry["lane"] for entry in job["strategy"]["matrix"]["include"]] == ["A", "B", "C"]
    assert job["needs"] == [
        "code-quality",
        "sales-volume-window",
        "sales-ui-tests",
        "weekly-report-role-regression",
        "weekly-report-source-audit",
    ]
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
    assert "A) roles=(admin)" in script
    assert "B) roles=(sales procurement)" in script
    assert "C) roles=(manager assistant)" in script
    assert 'for role in "${roles[@]}"' in script
    assert "run_phase 服务就绪检查 12" in script
    assert "run_phase 完整主回归 25" in script
    assert "run_phase 类目订单数对账 15" in script
    assert "run_phase 慢速排序与导出 40" in script
    assert "timeout --signal=TERM --kill-after=20s" in script
    assert ".runtime/reports/sales-volume-ci-logs/${SALES_VOLUME_ROLE}-${counter}.log" in script
    source_path = (
        Path(__file__).resolve().parents[2] / "modules" / "auto_test" / "tests" / "test_sales_volume_regression.py"
    )
    assert "REPORT_SERVICE_NOT_READY" in source_path.read_text(encoding="utf-8")
    assert 'export SALES_VOLUME_ROLE="$role"' in script
    assert "--basetemp" in script and "${SALES_VOLUME_ROLE}-${counter}" in script
    assert "overall=1" in script and 'exit "$overall"' in script
    assert "run_phase 采购来源对账" not in script
    assert "run_phase 采购管理员对账" not in script
    assert "run_phase 越权店铺" not in script
    for expected in (
        "test_multistore_sku_sales_against_order_items",
        "test_procurement_async_export_matches_query",
        "sort_regression.py",
        "-k async_export",
        "run_phase 采购异步导出",
        "test_dimension_specific_filter",
    ):
        assert expected in script
    weekly_job = workflow["jobs"]["weekly-report-role-regression"]
    assert weekly_job["needs"] == ["code-quality", "sales-ui-tests"]
    assert weekly_job["strategy"]["max-parallel"] == "1"
    crosschecks = workflow["jobs"]["sales-volume-admin-crosschecks"]
    crosscheck_script = {step.get("name"): step for step in crosschecks["steps"] if step.get("name")}[
        "Run administrator comparisons serially"
    ]["run"]
    for expected in (
        "test_procurement_source_data",
        "test_procurement_data_matches_administrator",
        "test_role_denied_store_with_administrator_sold_sample",
    ):
        assert expected in crosscheck_script
    assert crosschecks["needs"][-1] == "sales-volume-regression"
    assert "sales-volume-admin-crosschecks" in workflow["jobs"]["report"]["needs"]
    assert "sales-volume-admin-crosschecks" in workflow["jobs"]["collect-failure-logs"]["needs"]
    collector = workflow["jobs"]["collect-failure-logs"]
    assert "contains(needs.*.result, 'cancelled')" in collector["if"]
    collector_script = {step.get("name"): step for step in collector["steps"] if step.get("name")}[
        "Download each failed job log and annotations"
    ]["run"]
    assert 'job.get("conclusion") in {"failure", "cancelled"}' in collector_script
    scan = steps["Scan role test artifacts for secrets"]["run"]
    assert "for role in admin manager sales assistant procurement" in scan
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


def test_export_task_list_retries_transient_server_errors_only(monkeypatch):
    from modules.auto_test.tests import test_sales_volume_regression as report_tests

    class FakeResponse:
        def __init__(self, status, body):
            self.status_code = status
            self.headers = {"X-Request-ID": f"request-{status}"}
            self._body = body

        def json(self):
            return self._body

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"HTTP {self.status_code}")

    class FakeSession:
        def __init__(self):
            self.responses = [
                FakeResponse(503, {"code": 503, "msg": "temporary"}),
                FakeResponse(200, {"code": 200, "data": []}),
            ]
            self.calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return self.responses.pop(0)

    monkeypatch.setattr(report_tests.time, "sleep", lambda _: None)
    session = FakeSession()

    result = _fetch_export_task_page(session, "https://test.invalid", "商品销量报表_SKU维度", 1, 20)

    assert result == {"code": 200, "data": []}
    assert session.calls == 2


def test_export_task_list_does_not_retry_authentication_errors(monkeypatch):
    class FakeResponse:
        status_code = 200
        headers = {"X-Trace-ID": "trace-auth"}

        @staticmethod
        def json():
            return {"code": "401", "msg": "unauthorized"}

    class FakeSession:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            return FakeResponse()

    session = FakeSession()
    monkeypatch.setattr("modules.auto_test.tests.test_sales_volume_regression.time.sleep", lambda _: None)

    with pytest.raises(AssertionError, match="authentication failure"):
        _fetch_export_task_page(session, "https://test.invalid", "task", 1, 20)

    assert session.calls == 1


def test_export_task_list_stops_after_bounded_network_failures(monkeypatch):
    class FakeSession:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise requests.ConnectionError("connection refused")

    session = FakeSession()
    monkeypatch.setattr("modules.auto_test.tests.test_sales_volume_regression.time.sleep", lambda _: None)

    with pytest.raises(AssertionError, match="after 2 attempts"):
        _fetch_export_task_page(
            session,
            "https://test.invalid",
            "task",
            1,
            20,
            max_attempts=2,
        )

    assert session.calls == 2


def test_auth_failure_diagnostic_contains_session_context_without_credentials():
    response = SimpleNamespace(
        status_code=401,
        headers={"X-Request-ID": "req-123"},
    )
    auth_state = {
        "last_login_monotonic": 100.0,
        "login_count": 2,
        "refresh_count": 1,
    }

    diagnostic = _report_auth_failure_diagnostic(
        response,
        "querySkuSalesDimensionReport",
        {"code": 401, "msg": "not authorized", "token": "must-not-log"},
        "admin",
        auth_state,
    )

    assert diagnostic["role"] == "admin"
    assert diagnostic["endpoint"] == "querySkuSalesDimensionReport"
    assert diagnostic["http_status"] == 401
    assert diagnostic["app_code"] == 401
    assert diagnostic["request_id"] == "req-123"
    assert diagnostic["login_count"] == 2
    assert diagnostic["refresh_count"] == 1
    assert "token" not in diagnostic
    assert "message" not in diagnostic


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
        SimpleNamespace(getfixturevalue=lambda name: administrator_client),
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

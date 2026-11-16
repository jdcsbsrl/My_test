import base64
import json
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from modules.auto_test.core.sales_volume_contract import (
    DIMENSIONS,
    aggregate_orders,
    build_completed_report_window,
    build_export_task_name,
    category_order_counts,
    find_new_export_task,
    token_user_id,
    build_filter,
    group_sales_by_sku,
    order_source_breakdown,
    order_item_rows,
)


def test_filter_requires_time_and_supports_two_ranges_and_store_arrays():
    with pytest.raises(ValueError):
        build_filter()
    result = build_filter(
        ("2026-01-01 00:00:00", "2026-01-31 23:59:59"),
        ("2026-01-02 00:00:00", "2026-02-01 23:59:59"),
        ("store-1", "store-2"),
        ("2026-01-05 00:00:00", "2026-01-05 23:59:59"),
    )
    assert result["storeIds"] == ["store-1", "store-2"]
    assert result["payTimeBegin"] == "2026-01-01 00:00:00"
    assert result["sendDateBegin"] == "2026-01-02 00:00:00"
    assert result["createTimeBegin"] == "2026-01-05 00:00:00"
    assert result["createTimeEnd"] == "2026-01-05 23:59:59"


def test_filter_rejects_reversed_and_partial_ranges():
    with pytest.raises(ValueError):
        build_filter(("2026-02-01", "2026-01-01"))
    with pytest.raises(ValueError):
        build_filter(("2026-01-01",))
    with pytest.raises(ValueError):
        build_filter(("2026-01-01", "2026-01-31"), create_range=("2026-02-01", "2026-01-01"))
    with pytest.raises(ValueError):
        build_filter(("2026-01-01", "2026-01-31"), create_range=("2026-01-05",))


def test_report_window_uses_the_last_30_completed_days_from_a_shared_anchor():
    assert build_completed_report_window("2026-11-14") == (
        "2026-10-15 00:00:00",
        "2026-11-13 23:59:59",
    )
    assert build_completed_report_window("2026-11-14", days=1) == (
        "2026-11-13 00:00:00",
        "2026-11-13 23:59:59",
    )


def test_report_window_rejects_invalid_anchor_and_day_count():
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        build_completed_report_window("2026/11/14")
    with pytest.raises(ValueError, match="at least one day"):
        build_completed_report_window("2026-11-14", days=0)


def test_export_task_names_match_erp_dimension_defaults():
    assert build_export_task_name("sku") == "商品销量报表_SKU维度"
    assert build_export_task_name("store") == "商品销量报表_店铺维度"
    assert build_export_task_name("warehouse") == "商品销量报表_发货仓库维度"
    assert build_export_task_name("country") == "商品销量报表_国家维度"
    assert build_export_task_name("category") == "商品销量报表_类目维度"
    with pytest.raises(ValueError, match="Unsupported sales report dimension"):
        build_export_task_name("unknown")


def test_flatten_bundle_items_and_group_dimension_sales():
    items = list(order_item_rows([{"itemId": "A", "quantity": 1}, {"detail": [{"itemId": "B", "quantity": 2}]}]))
    assert [x["itemId"] for x in items] == ["A", "B"]
    assert group_sales_by_sku([{"itemId": "B", "salesNumber": "0.1"}, {"itemId": "B", "salesNumber": "0.2"}]) == {
        "B": Decimal("0.3")
    }
    with pytest.raises(ValueError):
        group_sales_by_sku([{"salesNumber": 1}])
    assert set(DIMENSIONS) == {"sku", "store", "warehouse", "country", "category"}


def test_order_aggregation_excludes_void_and_deduplicates_same_sku():
    orders = [{"orderNo": "one", "orderStatus": "0"}, {"orderNo": "void", "orderStatus": "6"}]
    details = {
        "one": [
            {"detail": [{"itemId": "A", "quantity": 2}, {"itemId": "A", "quantity": 1}, {"itemId": "B", "quantity": 1}]}
        ],
        "void": [{"itemId": "A", "quantity": 99}],
    }
    assert aggregate_orders(orders, details) == {
        "A": {"sales": 3, "orders": 1},
        "B": {"sales": 1, "orders": 1},
    }
    with pytest.raises(ValueError, match="Missing order details"):
        aggregate_orders(orders, {})


def test_bundle_sales_use_split_inventory_items_not_group_sku():
    orders = [{"orderNo": "one", "orderStatus": "0"}]
    details = {
        "one": [
            {"itemId": "G", "quantity": 2, "detail": [{"itemId": "A", "quantity": 4}, {"itemId": "B", "quantity": 2}]}
        ]
    }
    assert aggregate_orders(orders, details) == {
        "A": {"sales": 4, "orders": 1},
        "B": {"sales": 2, "orders": 1},
    }


def test_order_aggregation_ignores_removed_marketplace_lines():
    orders = [{"orderNo": "changed-order", "orderStatus": "0"}]
    details = {
        "changed-order": [
            {
                "itemId": "A",
                "quantity": 4,
                "platformChangeType": "REMOVED",
                "showRemoveTag": True,
            },
            {
                "itemId": "A",
                "quantity": 3,
                "platformChangeType": "ADDED",
                "showRemoveTag": False,
            },
            {
                "itemId": "B",
                "detail": [
                    {"itemId": "A", "quantity": 5, "showRemoveTag": True},
                    {"itemId": "B", "quantity": 2},
                ],
            },
        ]
    }

    assert aggregate_orders(orders, details) == {
        "A": {"sales": 3, "orders": 1},
        "B": {"sales": 2, "orders": 1},
    }


def test_order_source_breakdown_exposes_per_order_bundle_component_quantities():
    orders = [
        {"orderNo": "order-1", "orderStatus": "0", "payTime": "2026-11-12 10:00:00", "storeId": "store-1"},
        {"orderNo": "void-order", "orderStatus": "6", "storeId": "store-1"},
    ]
    details = {
        "order-1": [
            {
                "itemId": "GROUP-A",
                "groupSkuId": "GROUP-A",
                "detail": [{"itemId": "SKU-A", "quantity": 4}],
            },
            {"itemId": "SKU-A", "quantity": 88, "platformChangeType": "REMOVED", "showRemoveTag": True},
        ],
        "void-order": [{"itemId": "SKU-A", "quantity": 99}],
    }

    assert order_source_breakdown(orders, details, ["SKU-A"]) == {
        "SKU-A": [
            {
                "orderNo": "order-1",
                "orderStatus": "0",
                "itemId": "SKU-A",
                "quantity": 4,
                "payTime": "2026-11-12 10:00:00",
                "storeId": "store-1",
                "groupSkuId": "GROUP-A",
            }
        ]
    }


def test_category_order_count_deduplicates_multiple_skus_in_one_order():
    orders = [{"orderNo": "one", "orderStatus": "0"}, {"orderNo": "void", "orderStatus": "6"}]
    details = {
        "one": [{"itemId": "A", "quantity": 2}, {"itemId": "B", "quantity": 1}],
        "void": [{"itemId": "A", "quantity": 1}],
    }
    assert category_order_counts(orders, details, {"A": "category", "B": "category"}) == {"category": 1}
    with pytest.raises(ValueError, match="Missing category"):
        category_order_counts(orders, details, {"A": "category"})


def test_task_lookup_uses_new_task_id_and_detects_incomplete_results():
    pages = {
        1: {
            "code": 200,
            "total": 3,
            "rows": [
                {"id": "old-1", "taskName": "商品销量报表_SKU维度_20261116090000"},
                {"id": "old-2", "taskName": "商品销量报表_SKU维度_20261116090100"},
            ],
        },
        2: {
            "code": 200,
            "total": 3,
            "rows": [{"id": "new-1", "taskName": "商品销量报表_SKU维度_20261116090200", "status": "1"}],
        },
    }
    found = find_new_export_task(
        lambda page, size: pages[page], "商品销量报表_SKU维度", {"old-1", "old-2"}, page_size=2
    )
    assert found["status"] == "1" and found["id"] == "new-1"
    pages[1]["rows"] = []
    with pytest.raises(ValueError, match="pagination"):
        find_new_export_task(lambda page, size: pages[page], "商品销量报表_SKU维度", {"old-1", "old-2"}, page_size=2)


def test_task_lookup_correlates_default_name_by_creator_and_conditions():
    expected_conditions = {"storeIds": ["store-1", "store-2"], "exportReportType": 2}
    body = {
        "code": 200,
        "total": 4,
        "rows": [
            {
                "id": "old-task",
                "taskName": "商品销量报表_店铺维度_20261116090000",
                "createBy": "user-1",
                "taskConditions": json.dumps(expected_conditions),
            },
            {
                "id": "other-user",
                "taskName": "商品销量报表_店铺维度_20261116100000",
                "createBy": "user-2",
                "taskConditions": expected_conditions,
            },
            {
                "id": "other-conditions",
                "taskName": "商品销量报表_店铺维度_20261116100001",
                "createBy": "user-1",
                "taskConditions": {"storeIds": ["store-3"], "exportReportType": 2},
            },
            {
                "id": "current-task",
                "taskName": "商品销量报表_店铺维度_20261116100002",
                "createBy": "user-1",
                "taskConditions": json.dumps(expected_conditions),
                "status": "1",
            },
        ],
    }

    found = find_new_export_task(
        lambda page, size: body,
        "商品销量报表_店铺维度",
        {"old-task"},
        creator_id="user-1",
        expected_task_conditions=expected_conditions,
    )

    assert found and found["id"] == "current-task"


def test_token_user_id_reads_jwt_user_claim_without_returning_token():
    payload = base64.urlsafe_b64encode(json.dumps({"userId": 12345}).encode()).decode().rstrip("=")

    assert token_user_id(f"header.{payload}.signature") == "12345"
    assert token_user_id("not-a-jwt") is None


def test_export_workbook_download_retries_a_partially_published_file(monkeypatch):
    from modules.auto_test.tests import test_sales_volume_regression as report_tests

    workbook = Workbook()
    workbook.active.append(["SKU编码", "销量"])
    workbook.active.append(["SKU-1", 3])
    valid_file = BytesIO()
    workbook.save(valid_file)
    contents = [b"partial-xlsx", valid_file.getvalue()]

    class Response:
        status_code = 200
        headers = {"content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}

        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            return None

    class Session:
        calls = 0

        def get(self, url, timeout):
            content = contents[self.calls]
            self.calls += 1
            return Response(content)

    monkeypatch.setattr(report_tests.time, "sleep", lambda _: None)
    session = Session()
    content, loaded = report_tests._download_export_workbook(
        session, "https://files.invalid/export.xlsx?signature=secret", timeout=(1, 1), max_attempts=2
    )

    assert session.calls == 2
    assert content == valid_file.getvalue()
    assert list(loaded.active.values)[1] == ("SKU-1", 3)
    loaded.close()


def test_export_workbook_failure_diagnostics_hide_signed_url():
    from modules.auto_test.tests import test_sales_volume_regression as report_tests

    class Response:
        status_code = 200
        headers = {"content-type": "application/json", "content-length": "7"}
        content = b"not-xlsx"

        def raise_for_status(self):
            return None

    class Session:
        def get(self, url, timeout):
            return Response()

    with pytest.raises(AssertionError) as error:
        report_tests._download_export_workbook(
            Session(), "https://files.invalid/export.xlsx?signature=secret", timeout=(1, 1), max_attempts=1
        )

    assert "files.invalid/export.xlsx" not in str(error.value)
    assert "signature=secret" not in str(error.value)
    assert "downloadedBytes" in str(error.value)


def test_order_source_reconciliation_reads_all_pages():
    from modules.auto_test.tests.test_sales_volume_regression import _fetch_order_data

    class Response:
        def __init__(self, body):
            self.body = body

        def raise_for_status(self):
            pass

        def json(self):
            return self.body

    class Session:
        def post(self, url, json, timeout):
            if url.endswith("batchListNew"):
                number = str(json["pageNum"])
                return Response({"code": 200, "data": {"tableDataInfo": {"rows": [{"orderNo": number}], "total": 2}}})
            return Response({"code": 200, "data": {number: [] for number in json["orderNoList"]}})

    orders, details = _fetch_order_data(Session(), "https://test.invalid", ("start", "end"), ["store"])
    assert [row["orderNo"] for row in orders] == ["1", "2"]
    assert set(details) == {"1", "2"}


def test_combination_sku_list_omits_optional_search_parameter():
    from modules.auto_test.api.sku_group_api import SKUGroupAPI

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"code": 200, "total": 0, "rows": []}

    class Session:
        def get(self, url, params, timeout):
            self.params = params
            return Response()

    session = Session()
    api = SKUGroupAPI(session, "https://test.invalid")
    api.list_page(page_num=2, page_size=100)
    assert session.params == {"pageNum": 2, "pageSize": 100}
    api.list_page("group-a")
    assert session.params["groupSkuId"] == "group-a"

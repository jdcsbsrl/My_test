from datetime import datetime, timezone
from decimal import Decimal

import pytest

from modules.auto_test.core.sales_order_sort_audit import (
    ORDER_DETAILS_PATH,
    ORDER_LIST_PATH,
    PAUSED_REGRESSION_FIELDS,
    REGRESSION_FIELDS,
    SORT_FIELDS,
    UnmappedChannelId,
    UnmappedCountryCode,
    UnmappedStoreId,
    build_channel_name_map,
    build_country_code_map,
    build_store_name_map,
    classify_status,
    compare_values,
    evaluate_ordered_values,
    evaluate_values,
    extract_total_count,
    extract_order_details,
    extract_order_rows,
    normalize_sort_value,
    render_markdown_report,
    summarize_results,
    write_report,
)

pytestmark = pytest.mark.unit
PAUSED_PROFIT_LABEL = PAUSED_REGRESSION_FIELDS[0]


def field(label):
    return next(item for item in SORT_FIELDS if item.label == label)


def test_compare_values_detects_adjacent_ascending_and_descending_inversions():
    assert compare_values([1, 2, 2, 5], "asc") == []
    assert compare_values([5, 3, 4, 1], "asc") == [(5, 3), (4, 1)]
    assert compare_values([5, 3, 3, 1], "desc") == []
    assert compare_values([1, 4, 2], "desc") == [(1, 4)]


def test_evaluate_values_marks_empty_and_single_value_samples_inconclusive():
    assert evaluate_values([], "asc")["status"] == "inconclusive_insufficient_values"
    one_value = evaluate_values(["US", "US"], "desc")
    assert one_value["status"] == "inconclusive_insufficient_variation"


def test_unconfirmed_sort_oracles_are_warnings_and_do_not_block_ci():
    summary = summarize_results(
        [
            {"status": "inconclusive_snapshot_value_not_exposed"},
            {"status": "inconclusive_unmapped_channel"},
            {"status": "request_error"},
        ]
    )
    assert summary["overall"] == "warning"
    assert summary["exit_code"] == 0
    assert summary["severity_counts"] == {
        "passed": 0,
        "warning": 3,
        "failure": 0,
    }
    assert classify_status("request_error") == "warning"


def test_confirmed_sort_failure_is_distinct_from_non_blocking_warnings():
    summary = summarize_results(
        [
            {"status": "fail_nonmonotonic"},
            {"status": "inconclusive_snapshot_value_not_exposed"},
        ]
    )
    assert summary["overall"] == "failed"
    assert summary["exit_code"] == 1
    assert summary["severity_counts"] == {
        "passed": 0,
        "warning": 1,
        "failure": 1,
    }


def test_ordered_values_require_blanks_to_be_after_all_nonblank_values():
    valid = evaluate_ordered_values([1, 2, None, None], "asc")
    assert valid["status"] == "pass"
    assert valid["null_ordering"] == "pass"
    assert valid["null_count"] == 2

    invalid = evaluate_ordered_values([1, None, 2], "asc")
    assert invalid["status"] == "fail_null_not_last"
    assert invalid["null_ordering"] == "fail"
    assert invalid["nonnull_after_blank_count"] == 1


def test_ordered_values_distinguish_unobserved_blanks_from_a_passed_blank_check():
    result = evaluate_ordered_values([1, 2], "asc")
    assert result["status"] == "pass"
    assert result["null_ordering"] == "not_observed"


def test_country_values_are_compared_by_dictionary_short_code():
    country_codes = build_country_code_map(
        [
            {"dictLabel": "阿根廷", "dictValue": "AR"},
            {"dictLabel": "奥地利", "dictValue": "AT"},
        ]
    )
    country_field = field("国家")
    values = [
        normalize_sort_value(country_field, "阿根廷", country_codes),
        normalize_sort_value(country_field, "奥地利", country_codes),
    ]
    assert values == ["AR", "AT"]
    assert evaluate_values(values, "asc")["status"] == "pass"


def test_unmapped_country_is_not_silently_compared_by_display_name():
    with pytest.raises(UnmappedCountryCode):
        normalize_sort_value(field("国家"), "未知国家", {})


def test_store_values_are_compared_by_store_name_not_backend_id():
    stores = build_store_name_map(
        [
            {"id": "900", "name": "Beta Store"},
            {"id": "100", "name": "Alpha Store"},
        ]
    )
    values = [
        normalize_sort_value(field("店铺"), "100", store_names=stores),
        normalize_sort_value(field("店铺"), "900", store_names=stores),
    ]
    assert values == ["alpha store", "beta store"]
    assert evaluate_values(values, "asc")["status"] == "pass"


def test_store_id_without_name_mapping_is_not_silently_compared_as_an_id():
    with pytest.raises(UnmappedStoreId):
        normalize_sort_value(field("店铺"), "missing", store_names={})


def test_channel_values_are_compared_by_catalog_name_not_backend_id():
    channels = build_channel_name_map(
        [
            {"id": "900", "providerChannel": "Zulu Channel"},
            {"id": "100", "providerChannel": "Alpha Channel"},
        ]
    )
    values = [
        normalize_sort_value(field("物流渠道"), "100", channel_names=channels),
        normalize_sort_value(field("物流渠道"), "900", channel_names=channels),
    ]
    assert values == ["alpha channel", "zulu channel"]
    assert evaluate_values(values, "asc")["status"] == "pass"


def test_channel_id_without_catalog_name_is_not_silently_compared_as_an_id():
    with pytest.raises(UnmappedChannelId):
        normalize_sort_value(field("物流渠道"), "missing", channel_names={})


def test_numeric_and_datetime_values_are_normalized_for_comparison():
    amount = normalize_sort_value(field("订单金额"), "1,234.50")
    created = normalize_sort_value(field("创建日期"), "2026-09-27T10:00:00Z")
    assert amount == Decimal("1234.50")
    assert created == datetime(2026, 9, 27, 10, 0, tzinfo=timezone.utc)


def test_order_rows_are_extracted_from_api_envelope():
    body = {"code": 200, "data": {"list": [{"orderNo": "A"}, {"orderNo": "B"}], "total": 2}}
    assert extract_order_rows(body) == [{"orderNo": "A"}, {"orderNo": "B"}]


def test_order_total_is_extracted_from_table_response():
    body = {
        "code": 200,
        "data": {"tableDataInfo": {"rows": [{"orderNo": "A"}], "total": 897281}},
    }
    assert extract_total_count(body) == 897281


def test_order_details_are_extracted_from_order_number_map():
    body = {
        "code": 200,
        "data": {
            "A": [{"itemId": "SKU-1"}],
            "B": [{"itemId": "SKU-2"}],
        },
    }
    assert extract_order_details(body) == {
        "A": [{"itemId": "SKU-1"}],
        "B": [{"itemId": "SKU-2"}],
    }


def test_sort_inventory_contains_all_14_current_fields_in_ui_order():
    assert [item.label for item in SORT_FIELDS] == [
        "付款时间",
        "订单金额",
        "sku编码",
        "平台sku",
        "国家",
        "店铺",
        "物流渠道",
        "创建日期",
        "发货时间",
        "交运时间",
        "物流单号",
        "利润",
        "利润率",
        "转入WMS的时间",
    ]


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


class FakeOrderListClient:
    def __init__(self):
        self.post_calls = []

    def post(self, path, *, json, timeout):
        self.post_calls.append((path, json, timeout))
        timestamps = [
            "2026-09-25T10:00:00Z",
            "2026-09-26T10:00:00Z",
            "2026-09-27T10:00:00Z",
        ]
        if json["isAsc"] == "desc":
            timestamps.reverse()
        return FakeResponse(
            {
                "code": 200,
                "data": {"rows": [{"createTime": value} for value in timestamps]},
            }
        )


def test_auditor_checks_creation_date_in_both_directions_without_live_api():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    client = FakeOrderListClient()
    report = SalesOrderSortAuditor(
        client,
        "test",
        page_size=10,
        max_pages=1,
    ).run([field("创建日期")])

    assert report["overall"] == "passed"
    assert [item["status"] for item in report["results"]] == ["pass", "pass"]
    assert [call[1]["orderByColumn"] for call in client.post_calls] == [
        "create_time",
        "create_time",
    ]
    assert [call[1]["isAsc"] for call in client.post_calls] == ["asc", "desc"]


def test_auditor_can_check_only_an_unconfirmed_direction():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    client = FakeOrderListClient()
    report = SalesOrderSortAuditor(client, "test", page_size=10, max_pages=1).run(
        [field("创建日期")], directions=("desc",)
    )

    assert report["overall"] == "passed"
    assert report["directions"] == ["desc"]
    assert [item["direction"] for item in report["results"]] == ["desc"]
    assert [call[1]["isAsc"] for call in client.post_calls] == ["desc"]


def test_cli_preview_does_not_execute_api_calls(capsys):
    from modules.auto_test.core.sales_order_sort_audit import main

    assert main(["--env", "test"]) == 0
    output = capsys.readouterr().out
    assert "fields=13, directions=26" in output
    assert "paused_fields=" + PAUSED_PROFIT_LABEL in output


def test_cli_preview_counts_only_requested_directions(capsys):
    from modules.auto_test.core.sales_order_sort_audit import main

    assert main(["--env", "test", "--field", "国家", "--direction", "desc"]) == 0
    assert "fields=1, directions=1" in capsys.readouterr().out


def test_cli_can_explicitly_preview_the_temporarily_paused_profit_field(capsys):
    from modules.auto_test.core.sales_order_sort_audit import main

    assert main(["--env", "test", "--field", PAUSED_PROFIT_LABEL]) == 0
    assert "fields=1, directions=2" in capsys.readouterr().out


def test_default_regression_scope_pauses_profit_but_keeps_all_ui_fields_registered():
    assert PAUSED_REGRESSION_FIELDS == (PAUSED_PROFIT_LABEL,)
    assert len(SORT_FIELDS) == 14
    assert len(REGRESSION_FIELDS) == 13
    assert PAUSED_PROFIT_LABEL not in {item.label for item in REGRESSION_FIELDS}
    assert PAUSED_PROFIT_LABEL in {item.label for item in SORT_FIELDS}


def test_auto_test_module_entrypoint_dispatches_preview_without_api_calls(capsys):
    from modules.auto_test.__main__ import main as auto_test_main

    assert auto_test_main(["sort-audit", "--env", "test"]) == 0
    output = capsys.readouterr().out
    assert "fields=13, directions=26" in output
    assert "paused_fields=" + PAUSED_PROFIT_LABEL in output


def test_default_auditor_run_omits_paused_profit_and_reports_it(monkeypatch):
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    auditor = SalesOrderSortAuditor(object(), "test")
    monkeypatch.setattr(auditor, "_load_country_codes", lambda: {})
    monkeypatch.setattr(auditor, "_load_store_names", lambda: {})
    monkeypatch.setattr(auditor, "_load_channel_names", lambda: {})
    monkeypatch.setattr(
        auditor,
        "_audit_direction",
        lambda field, direction, *_: {"field": field.label, "direction": direction, "status": "pass"},
    )

    report = auditor.run(directions=("asc",))

    assert report["paused_fields"] == [PAUSED_PROFIT_LABEL]
    assert len(report["results"]) == 13
    assert PAUSED_PROFIT_LABEL not in {item["field"] for item in report["results"]}


class FakeStoreClient:
    def get(self, path, *, timeout):
        return FakeResponse(
            {
                "code": 200,
                "data": [
                    {"id": "2", "name": "Beta"},
                    {"id": "1", "name": "Alpha"},
                ],
            }
        )

    def post(self, path, *, json, timeout):
        assert path == ORDER_LIST_PATH
        rows = [{"storeId": "1"}, {"storeId": "2"}]
        if json["isAsc"] == "desc":
            rows.reverse()
        return FakeResponse({"code": 200, "data": {"rows": rows}})


def test_auditor_uses_store_directory_names_for_both_directions():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakeStoreClient(), "test", page_size=10, max_pages=1).run([field("店铺")])
    assert report["overall"] == "warning"
    assert [item["status"] for item in report["results"]] == [
        "inconclusive_database_collation",
        "inconclusive_database_collation",
    ]
    assert report["store_name_dictionary_entries"] == 2


class FakeChannelClient:
    def get(self, path, *, timeout):
        from modules.auto_test.core.sales_order_sort_audit import CHANNEL_CATALOG_PATH

        assert path == CHANNEL_CATALOG_PATH
        return FakeResponse(
            {
                "code": 200,
                "data": [
                    {"id": "900", "providerChannel": "Zulu Channel"},
                    {"id": "100", "providerChannel": "Alpha Channel"},
                ],
            }
        )

    def post(self, path, *, json, timeout):
        assert path == ORDER_LIST_PATH
        rows = [
            {"providerChannelId": "100"},
            {"providerChannelId": "900"},
        ]
        if json["isAsc"] == "desc":
            rows.reverse()
        return FakeResponse({"code": 200, "data": {"rows": rows}})


def test_auditor_checks_logistics_channel_names_in_both_directions():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakeChannelClient(), "test", page_size=10, max_pages=1).run([field("物流渠道")])
    assert report["overall"] == "warning"
    assert [item["status"] for item in report["results"]] == [
        "inconclusive_database_collation",
        "inconclusive_database_collation",
    ]
    assert report["channel_name_dictionary_entries"] == 2
    assert all(item["response_key"] == "providerChannelId" for item in report["results"])


class FakeTextSortClient:
    def post(self, path, *, json, timeout):
        assert path == ORDER_LIST_PATH
        # Python Unicode code-point order sees this as an ascending inversion.
        return FakeResponse({"code": 200, "data": {"rows": [{"trackingNumber": "a"}, {"trackingNumber": "B"}]}})


def test_text_sort_codepoint_inversion_is_warning_without_database_collation_oracle():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakeTextSortClient(), "test", page_size=10, max_pages=1).run(
        [field("物流单号")], directions=("asc",)
    )
    result = report["results"][0]
    assert report["overall"] == "warning"
    assert result["status"] == "inconclusive_database_collation"
    assert result["severity"] == "warning"
    assert result["inversions"] is None


class FakeUnknownChannelClient(FakeChannelClient):
    def get(self, path, *, timeout):
        return FakeResponse({"code": 200, "data": [{"id": "999", "providerChannel": "Unrelated"}]})


def test_unmapped_channel_values_are_reported_as_warning_not_request_error():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakeUnknownChannelClient(), "test", page_size=10, max_pages=1).run(
        [field("物流渠道")], directions=("asc",)
    )
    result = report["results"][0]
    assert result["status"] == "inconclusive_unmapped_channel"
    assert result["severity"] == "warning"


class FakeTextNullOrderClient:
    def post(self, path, *, json, timeout):
        assert path == ORDER_LIST_PATH
        return FakeResponse({"code": 200, "data": {"rows": [{"trackingNumber": None}, {"trackingNumber": "A1"}]}})


def test_text_nulls_not_last_remains_a_confirmed_failure_without_collation_oracle():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakeTextNullOrderClient(), "test", page_size=10, max_pages=1).run(
        [field("物流单号")], directions=("asc",)
    )
    result = report["results"][0]
    assert report["overall"] == "failed"
    assert result["status"] == "fail_null_not_last"
    assert result["severity"] == "failure"


class FakeSkuClient:
    def post(self, path, *, json, timeout):
        if path == ORDER_LIST_PATH:
            rows = [{"orderNo": "A"}, {"orderNo": "B"}]
            return FakeResponse({"code": 200, "data": {"rows": rows}})
        assert path == ORDER_DETAILS_PATH
        return FakeResponse(
            {
                "code": 200,
                "data": {
                    "A": [{"itemId": "A1"}, {"itemId": "Z9"}],
                    "B": [{"itemId": "B1"}, {"itemId": "C9"}],
                },
            }
        )


def test_sku_sort_uses_minimum_for_ascending_and_maximum_for_descending():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakeSkuClient(), "test", page_size=10, max_pages=1).run([field("sku编码")])
    assert report["overall"] == "warning"
    assert report["exit_code"] == 0
    assert [item["severity"] for item in report["results"]] == ["warning", "warning"]
    assert [item["selected_sku_aggregation"] for item in report["results"]] == [
        "min",
        "max",
    ]
    assert [item["status"] for item in report["results"]] == [
        "inconclusive_snapshot_value_not_exposed",
        "inconclusive_snapshot_value_not_exposed",
    ]
    assert [item["detail_derived_diagnostic_status"] for item in report["results"]] == ["pass", "pass"]
    assert all(item["snapshot_stability"] == "not_verifiable_read_only" for item in report["results"])


class FakePagedOrderClient:
    def post(self, path, *, json, timeout):
        assert path == ORDER_LIST_PATH
        values = list(range(1, 27))
        if json["isAsc"] == "desc":
            values.reverse()
        start = (json["pageNum"] - 1) * json["pageSize"]
        rows = [{"createTime": f"2026-09-{value:02d}T10:00:00Z"} for value in values[start : start + json["pageSize"]]]
        return FakeResponse(
            {
                "code": 200,
                "data": {"tableDataInfo": {"rows": rows, "total": 26}},
            }
        )


def test_markdown_report_calls_unconfirmed_sort_evidence_warning():
    content = render_markdown_report(
        {
            "environment": "test",
            "paused_fields": [PAUSED_PROFIT_LABEL],
            "overall": "warning",
            "exit_code": 0,
            "read_only": True,
            "results": [
                {
                    "field": "平台sku",
                    "direction": "asc",
                    "status": "inconclusive_snapshot_value_not_exposed",
                    "severity": "warning",
                    "detail_derived_diagnostic_status": "pass",
                    "row_count": 400,
                    "nonnull_count": 200,
                    "inversions": 0,
                    "sampled_pages": [1, 2, 251],
                }
            ],
        }
    )
    assert "总体判定：**WARNING**" in content
    assert "WARNING" in content
    assert "不阻断 CI" in content
    assert "\u6682\u7f13\u56de\u5f52\u5b57\u6bb5\uff1a" + PAUSED_PROFIT_LABEL in content
    assert "冻结排序快照键未从订单列表接口透出" in content


def test_write_report_creates_json_and_markdown_in_runtime_reports(tmp_path, monkeypatch):
    from modules.trae_test.utils import runtime_paths

    monkeypatch.setattr(runtime_paths, "runtime_dir", lambda kind: tmp_path)
    report = {
        "environment": "test",
        "overall": "warning",
        "exit_code": 0,
        "severity_counts": {"passed": 0, "warning": 1, "failure": 0},
        "read_only": True,
        "results": [],
    }

    json_path = write_report(report)
    markdown_path = json_path.with_suffix(".md")

    assert json_path.is_file()
    assert markdown_path.is_file()
    assert "WARNING" in markdown_path.read_text(encoding="utf-8")


def test_auditor_checks_sampled_pages_and_the_dataset_tail():
    from modules.auto_test.core.sales_order_sort_audit import SalesOrderSortAuditor

    report = SalesOrderSortAuditor(FakePagedOrderClient(), "test", page_size=2, max_pages=2).run([field("创建日期")])
    assert report["overall"] == "passed"
    assert [item["sampled_pages"] for item in report["results"]] == [
        [1, 2, 13],
        [1, 2, 13],
    ]
    assert [item["total_count"] for item in report["results"]] == [26, 26]
    assert [item["row_count"] for item in report["results"]] == [6, 6]

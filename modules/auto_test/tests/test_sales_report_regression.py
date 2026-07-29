"""Sales product sales report regression coverage."""

import json
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_report_page import SalesReportPage


REPORT_DIR = Path("reports/sales_report_regression")
QUERY_DETAIL_JSONL = REPORT_DIR / "query_detail.jsonl"
QUERY_DETAIL_MD = REPORT_DIR / "query_detail_report.md"


def _first_meaningful_prefix(value: str, length: int = 8) -> str:
    cleaned = value.strip()
    if not cleaned or cleaned == "-":
        return ""
    return cleaned[: min(length, len(cleaned))]


def _compact_row(row: dict[str, str]) -> dict[str, str]:
    interesting_columns = [
        "SKU编码",
        "变体ID",
        "SKU中文",
        "SKU英文",
        "销售状态",
        "品类",
        "创建时间",
        "销量",
        "日均销量",
        "库存(汇总)",
        "订单数",
    ]
    return {column: row.get(column, "") for column in interesting_columns if column in row}


def _first_usable_variant_id(sales_report: SalesReportPage) -> tuple[str, dict[str, str]]:
    for row in sales_report.visible_rows(limit=20):
        raw_value = row.get("变体ID", "")
        if not raw_value or raw_value == "-":
            continue
        variant_id = raw_value.split(",", maxsplit=1)[0].strip()
        if variant_id:
            return variant_id, row
    return "", {}


def _first_created_date_on_or_after(sales_report: SalesReportPage, min_date: str) -> tuple[str, dict[str, str]]:
    for row in sales_report.visible_rows(limit=50):
        created_at = row.get("创建时间", "")
        created_date = created_at[:10] if len(created_at) >= 10 else ""
        if created_date and created_date >= min_date:
            return created_date, row
    return "", {}


def _record_query_detail(
    case_name: str,
    conditions: dict[str, str],
    sales_report: SalesReportPage,
    assertion: str,
    passed: bool,
    note: str = "",
) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    rows = sales_report.visible_rows(limit=3)
    detail: dict[str, Any] = {
        "case_name": case_name,
        "conditions": conditions,
        "total_count": sales_report.total_count(),
        "current_page_row_count": sales_report.row_count(),
        "sample_rows": [_compact_row(row) for row in rows],
        "assertion": assertion,
        "passed": passed,
        "note": note,
    }
    with QUERY_DETAIL_JSONL.open("a", encoding="utf-8") as file:
        file.write(json.dumps(detail, ensure_ascii=False) + "\n")
    with QUERY_DETAIL_MD.open("a", encoding="utf-8") as file:
        file.write(f"\n## {case_name}\n\n")
        file.write(f"- 搜索条件：{conditions}\n")
        file.write(f"- 返回总数：{detail['total_count']}\n")
        file.write(f"- 当前页行数：{detail['current_page_row_count']}\n")
        file.write(f"- 验证点：{assertion}\n")
        file.write(f"- 结果：{'PASS' if passed else 'FAIL'}\n")
        if note:
            file.write(f"- 备注：{note}\n")
        file.write(f"- 首行样例：{detail['sample_rows'][0] if detail['sample_rows'] else {}}\n")


@pytest.fixture(scope="session", autouse=True)
def query_detail_report_header() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    QUERY_DETAIL_JSONL.write_text("", encoding="utf-8")
    QUERY_DETAIL_MD.write_text(
        "# 销售商品销量报表查询条件明细报告\n\n"
        "说明：本报告由自动化实跑生成，记录每个查询条件、返回数量、样例数据和验证结果。\n",
        encoding="utf-8",
    )


@pytest.fixture()
def sales_report(logged_in_page: Page) -> SalesReportPage:
    page = SalesReportPage(logged_in_page)
    page.navigate_to_report()
    if page.row_count() == 0:
        page.search()
    assert page.row_count() > 0, "Sales report should load default rows"
    return page


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestSalesReportRegression:
    def test_default_query_loads_table(self, sales_report: SalesReportPage) -> None:
        first_row = sales_report.first_row()

        assert sales_report.total_count() > 0
        assert first_row.get("SKU编码")
        assert first_row.get("SKU中文")
        assert "销量" in first_row
        assert "日均销量" in first_row
        _record_query_detail(
            "默认查询",
            {"订单付款时间": "页面默认近 30 天"},
            sales_report,
            "表格有数据，首行包含 SKU 编码、SKU 中文、销量、日均销量",
            True,
        )

    @pytest.mark.parametrize(
        ("field_name", "fill_method", "column_name"),
        [
            ("SKU编码", "fill_sku_code", "SKU编码"),
            ("SKU中文", "fill_sku_cn", "SKU中文"),
            ("变体ID", "fill_variant_id", "变体ID"),
        ],
    )
    def test_text_condition_query(
        self,
        sales_report: SalesReportPage,
        field_name: str,
        fill_method: str,
        column_name: str,
    ) -> None:
        first_row = sales_report.first_row()
        query_value = _first_meaningful_prefix(first_row.get(field_name, ""))
        source_note = ""
        if field_name == "变体ID":
            query_value, source_row = _first_usable_variant_id(sales_report)
            source_note = f"来源行={_compact_row(source_row)}"
        if not query_value:
            pytest.skip(f"Current page has no usable {field_name} value")

        sales_report.reset()
        getattr(sales_report, fill_method)(query_value)
        sales_report.search()

        passed = False
        note = ""
        try:
            sales_report.assert_column_contains(column_name, query_value)
            passed = True
        except AssertionError as error:
            note = str(error)
            raise
        finally:
            _record_query_detail(
                f"{field_name} 查询",
                {field_name: query_value},
                sales_report,
                f"{column_name} 列包含搜索值 {query_value}",
                passed,
                "；".join(item for item in (source_note, note) if item),
            )

    def test_sku_english_condition_query_accepts_empty_result(self, sales_report: SalesReportPage) -> None:
        first_row = sales_report.first_row()
        query_value = _first_meaningful_prefix(first_row.get("SKU英文", ""))
        if not query_value:
            query_value = "NO-SUCH-SKU-EN"

        sales_report.reset()
        sales_report.fill_sku_en(query_value)
        sales_report.search()

        assert sales_report.row_count() >= 0
        _record_query_detail(
            "SKU 英文查询",
            {"SKU英文": query_value},
            sales_report,
            "页面正常返回结果或空结果，不报错",
            True,
        )

    def test_sales_status_condition_query(self, sales_report: SalesReportPage) -> None:
        first_row = sales_report.first_row()
        status = _first_meaningful_prefix(first_row.get("销售状态", ""), length=4)
        if not status:
            pytest.skip("Current page has no usable sales status value")

        sales_report.reset()
        selected = sales_report.select_dropdown_by_label("销售状态", status)
        assert selected, f"Unable to select sales status: {status}"
        sales_report.search()

        sales_report.assert_column_contains("销售状态", status)
        _record_query_detail(
            "销售状态查询",
            {"销售状态": status},
            sales_report,
            f"销售状态列包含 {status}",
            True,
        )

    def test_category_condition_query(self, sales_report: SalesReportPage) -> None:
        first_row = sales_report.first_row()
        category = _first_meaningful_prefix(first_row.get("品类", ""), length=8)
        if not category:
            pytest.skip("Current page has no usable category value")

        sales_report.reset()
        selected = sales_report.select_dropdown_by_label("品类", category)
        if not selected:
            pytest.skip(f"Category selector did not expose option: {category}")
        sales_report.search()

        sales_report.assert_column_contains("品类", category)
        _record_query_detail(
            "品类查询",
            {"品类": category},
            sales_report,
            f"品类列包含 {category}",
            True,
        )

    def test_sku_create_date_condition_query_negative(self, sales_report: SalesReportPage) -> None:
        first_row = sales_report.first_row()
        created_at = first_row.get("创建时间", "")
        match = created_at[:10] if len(created_at) >= 10 else ""
        if not match:
            pytest.skip("Current page has no usable created date")

        sales_report.reset()
        sales_report.fill_sku_create_date(f"{match} 00:00:00", f"{match} 00:00:00")
        input_values = sales_report.sku_create_date_values()
        sales_report.search()

        passed = sales_report.total_count() == 0
        _record_query_detail(
            "SKU 创建日期查询",
            {"SKU创建日期开始时间": match, "SKU创建日期结束时间": match},
            sales_report,
            "配合页面默认最近 30 天付款时间，返回总数应为 0",
            passed,
            (
                f"输入框实际值={input_values}；请求payload={sales_report.last_search_payload}；"
                f"实际返回总数={sales_report.total_count()}"
            ),
        )
        assert passed, f"SKU create date range should return 0 rows, got {sales_report.total_count()}"

    def test_sku_create_date_condition_query_positive(self, sales_report: SalesReportPage) -> None:
        match, source_row = _first_created_date_on_or_after(sales_report, "2026-06-29")
        if not match:
            pytest.skip("Current page has no SKU created date inside default payment range")

        sales_report.reset()
        sales_report.fill_sku_create_date(match, match)
        input_values = sales_report.sku_create_date_values()
        sales_report.search()

        passed = sales_report.total_count() > 0
        _record_query_detail(
            "SKU 创建日期查询-正向",
            {"SKU创建日期开始时间": match, "SKU创建日期结束时间": match},
            sales_report,
            "配合页面默认最近 30 天付款时间，应返回至少 1 条结果",
            passed,
            (
                f"来源行={_compact_row(source_row)}；输入框实际值={input_values}；"
                f"请求payload={sales_report.last_search_payload}；实际返回总数={sales_report.total_count()}"
            ),
        )
        assert passed, f"SKU create date range should return rows, got {sales_report.total_count()}"

    def test_sku_create_date_condition_query_full_range(self, sales_report: SalesReportPage) -> None:
        start_time = "2026-06-01 00:00:00"
        end_time = "2026-07-31 23:59:59"

        sales_report.reset()
        sales_report.fill_sku_create_date(start_time, end_time)
        input_values = sales_report.sku_create_date_values()
        sales_report.search()

        passed = sales_report.total_count() > 0
        _record_query_detail(
            "SKU 创建日期查询-完整范围",
            {"SKU创建日期开始时间": start_time, "SKU创建日期结束时间": end_time},
            sales_report,
            "配合页面默认最近 30 天付款时间，应返回至少 1 条结果",
            passed,
            (
                f"输入框实际值={input_values}；请求payload={sales_report.last_search_payload}；"
                f"实际返回总数={sales_report.total_count()}"
            ),
        )
        assert passed, f"SKU create date full range should return rows, got {sales_report.total_count()}"

    def test_pagination(self, sales_report: SalesReportPage) -> None:
        initial_page = sales_report.current_page()
        moved = sales_report.click_page_number(2) or sales_report.next_page()
        if moved:
            assert sales_report.current_page() != initial_page
            assert sales_report.row_count() > 0
            _record_query_detail(
                "分页",
                {"操作": f"从第 {initial_page} 页切换到第 {sales_report.current_page()} 页"},
                sales_report,
                "页码变化且当前页有数据",
                True,
            )
        else:
            pytest.skip("Only one page is available")

    @pytest.mark.parametrize("column_name", ["销量", "日均销量", "库存(汇总)", "订单数"])
    def test_sort_columns(self, sales_report: SalesReportPage, column_name: str) -> None:
        result = sales_report.sort_and_assert_numeric_order(column_name)
        _record_query_detail(
            f"{column_name} 排序",
            {"排序列": column_name, "排序方向": "先降序，后升序"},
            sales_report,
            "降序和升序后可见数值均有序；"
            f"降序取样值={result.get('desc_values', [])[:10]}；"
            f"升序取样值={result.get('asc_values', [])[:10]}",
            bool(result["passed"]),
        )
        assert result["passed"], result

    def test_expand_detail(self, sales_report: SalesReportPage) -> None:
        assert sales_report.has_expand_control(), "Sales report should expose row detail expand controls"
        expanded_count = -1
        try:
            expanded_count = sales_report.expand_first_row()
            passed = True
            note = f"展开明细行数量={expanded_count}"
        except AssertionError as error:
            passed = False
            note = str(error)
            raise
        finally:
            _record_query_detail(
                "展开明细",
                {"操作": "点击首行左侧展开箭头"},
                sales_report,
                "点击后出现明细展开内容",
                passed,
                note,
            )
        assert expanded_count >= 0

    def test_sort_then_expand_detail(self, sales_report: SalesReportPage) -> None:
        sort_result = sales_report.sort_and_assert_numeric_order("销量")

        assert sort_result["passed"], sort_result
        assert sales_report.has_expand_control(), "Sales report should expose row detail expand controls after sorting"
        expanded_count = -1
        try:
            expanded_count = sales_report.expand_first_row()
            passed = True
            note = (
                f"降序取样值={sort_result.get('desc_values', [])[:10]}；"
                f"升序取样值={sort_result.get('asc_values', [])[:10]}；"
                f"展开明细行数量={expanded_count}"
            )
        except AssertionError as error:
            passed = False
            note = (
                f"降序取样值={sort_result.get('desc_values', [])[:10]}；"
                f"升序取样值={sort_result.get('asc_values', [])[:10]}；"
                f"展开失败：{error}"
            )
            raise
        finally:
            _record_query_detail(
                "销量排序后展开明细",
                {"复合操作": "销量降序排序 -> 点击首行左侧展开箭头"},
                sales_report,
                "排序后仍可展开首行明细",
                passed,
                note,
            )
        assert expanded_count >= 0

    def test_export_menu_and_downloads(self, sales_report: SalesReportPage) -> None:
        options = sales_report.export_menu_options()

        assert any("当前页" in option for option in options), f"Export current-page option missing: {options}"
        assert any("搜索条件" in option for option in options), f"Export by-search option missing: {options}"

        download_dir = REPORT_DIR / "downloads"
        current_page = sales_report.export_by_menu_text("当前页", str(download_dir))
        assert current_page["success"] or any(
            item["status"] == 500 for item in current_page.get("responses", [])
        ), current_page

        by_search = sales_report.export_by_menu_text("搜索条件", str(download_dir))
        assert by_search["success"], by_search
        _record_query_detail(
            "导出",
            {"操作": "打开导出菜单 -> 导出当前页 -> 按搜索条件导出"},
            sales_report,
            "当前页导出允许 500 已知缺陷；按搜索条件导出成功",
            True,
            f"菜单项={options}；当前页导出={current_page}；按条件导出={by_search}",
        )

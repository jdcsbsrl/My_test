"""Test export flow with order data passed from search page.

测试流程：排序→设置分页→勾选全部→导出勾选订单→选择模板→全选字段→实时导出
验证导出数据顺序与页面排序一致
"""

import pytest
from playwright.sync_api import Page

from modules.auto_test.facades.sales_order_facade import SalesOrderFacade
from modules.auto_test.pages.sales_order_export_page import EXPORT_TEMPLATE


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestExportWithOrderData:
    """Test export flow with order data."""

    def test_export_sort_payment_time_asc(self, logged_in_page: Page) -> None:
        """Test export with payment time ascending sort."""
        facade = SalesOrderFacade(logged_in_page)

        print("\n" + "=" * 70)
        print("Step 1: Navigate to sales order page")
        print("=" * 70)
        facade.navigate_to_sales_order()
        print(f"URL: {logged_in_page.url}")

        print("\n" + "=" * 70)
        print("Step 2: Click search button")
        print("=" * 70)
        facade.click_search()

        print("\n" + "=" * 70)
        print("Step 3: Select payment time ascending sort")
        print("=" * 70)
        facade.select_sort("付款时间", is_ascending=True)

        print("\n" + "=" * 70)
        print("Step 4: Set page size to 50")
        print("=" * 70)
        facade.set_page_size(50)

        print("\n" + "=" * 70)
        print("Step 5: Select all orders on current page")
        print("=" * 70)
        selected_count = facade.select_all_current_page()
        print(f"✅ Selected {selected_count} orders")
        assert selected_count > 0, "当前页没有可导出的订单"

        print("\n" + "=" * 70)
        print("Step 6: Get page order numbers for verification")
        print("=" * 70)
        page_order_numbers = facade.get_sorted_order_numbers(50)
        print(f"✅ Got {len(page_order_numbers)} order numbers for verification")
        assert page_order_numbers, "页面未返回订单号，无法验证导出顺序"
        if page_order_numbers:
            print(f"   First 10: {page_order_numbers[:10]}")

        print("\n" + "=" * 70)
        print("Step 7: Export selected orders")
        print("=" * 70)
        export_result = facade.export_selected(
            select_all_fields=False, template_name=EXPORT_TEMPLATE, ensure_fields=["系统单号"]
        )

        assert export_result["success"], f"导出下载失败: {export_result.get('error')}"
        print("\n✅ Export download successful")
        print(f"   - Filename: {export_result['filename']}")
        print(f"   - File path: {export_result['file_path']}")
        print(f"   - File size: {export_result['file_size']} bytes")

        file_verify = SalesOrderFacade.verify_export_file(export_result["file_path"])
        assert file_verify["valid"], f"导出文件校验失败: {file_verify}"
        consistency = SalesOrderFacade.verify_export_order_consistency(
            export_result["file_path"], page_order_numbers
        )
        assert consistency["success"], f"导出顺序不一致: {consistency}"

        print("\n" + "=" * 70)
        print("Test completed")
        print("=" * 70)

    def test_export_sort_payment_time_desc(self, logged_in_page: Page) -> None:
        """Test export with payment time descending sort."""
        facade = SalesOrderFacade(logged_in_page)

        print("\n" + "=" * 70)
        print("Step 1: Navigate to sales order page")
        print("=" * 70)
        facade.navigate_to_sales_order()

        print("\n" + "=" * 70)
        print("Step 2: Click search button")
        print("=" * 70)
        facade.click_search()

        print("\n" + "=" * 70)
        print("Step 3: Select payment time descending sort")
        print("=" * 70)
        facade.select_sort("付款时间", is_ascending=False)

        print("\n" + "=" * 70)
        print("Step 4: Set page size to 20")
        print("=" * 70)
        facade.set_page_size(20)

        print("\n" + "=" * 70)
        print("Step 5: Select all orders on current page")
        print("=" * 70)
        selected_count = facade.select_all_current_page()
        print(f"✅ Selected {selected_count} orders")
        assert selected_count > 0, "当前页没有可导出的订单"

        print("\n" + "=" * 70)
        print("Step 6: Get page order numbers for verification")
        print("=" * 70)
        page_order_numbers = facade.get_sorted_order_numbers(20)
        print(f"✅ Got {len(page_order_numbers)} order numbers")
        assert page_order_numbers, "页面未返回订单号，无法验证导出顺序"

        print("\n" + "=" * 70)
        print("Step 7: Export selected orders")
        print("=" * 70)
        export_result = facade.export_selected(
            select_all_fields=False, template_name=EXPORT_TEMPLATE, ensure_fields=["系统单号"]
        )

        assert export_result["success"], f"导出失败: {export_result.get('error')}"
        print(f"\n✅ Export successful: {export_result['file_path']}")
        consistency = SalesOrderFacade.verify_export_order_consistency(
            export_result["file_path"], page_order_numbers
        )
        assert consistency["success"], f"导出顺序不一致: {consistency}"

        print("\n" + "=" * 70)
        print("Test completed")
        print("=" * 70)

    def test_export_sort_order_amount_asc(self, logged_in_page: Page) -> None:
        """Test export with order amount ascending sort."""
        facade = SalesOrderFacade(logged_in_page)

        print("\n" + "=" * 70)
        print("Step 1: Navigate to sales order page")
        print("=" * 70)
        facade.navigate_to_sales_order()

        print("\n" + "=" * 70)
        print("Step 2: Click search button")
        print("=" * 70)
        facade.click_search()

        print("\n" + "=" * 70)
        print("Step 3: Select order amount ascending sort")
        print("=" * 70)
        facade.select_sort("订单金额", is_ascending=True)

        print("\n" + "=" * 70)
        print("Step 4: Set page size to 10")
        print("=" * 70)
        facade.set_page_size(10)

        print("\n" + "=" * 70)
        print("Step 5: Select all orders on current page")
        print("=" * 70)
        selected_count = facade.select_all_current_page()
        print(f"✅ Selected {selected_count} orders")
        assert selected_count > 0, "当前页没有可导出的订单"

        print("\n" + "=" * 70)
        print("Step 6: Export selected orders")
        print("=" * 70)
        export_result = facade.export_selected(
            select_all_fields=False, template_name=EXPORT_TEMPLATE, ensure_fields=["系统单号"]
        )

        assert export_result["success"], f"导出失败: {export_result.get('error')}"
        print(f"\n✅ Export successful: {export_result['file_path']}")
        file_verify = SalesOrderFacade.verify_export_file(export_result["file_path"])
        assert file_verify["valid"], f"导出文件校验失败: {file_verify}"

        print("\n" + "=" * 70)
        print("Test completed")
        print("=" * 70)

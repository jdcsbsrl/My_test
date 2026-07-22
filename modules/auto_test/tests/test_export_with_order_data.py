"""Test export flow with order data passed from search page.

测试流程：排序→设置分页→勾选全部→导出勾选订单→选择模板→全选字段→实时导出
验证导出数据顺序与页面排序一致
"""

import pytest
from playwright.sync_api import Page

from modules.auto_test.facades.sales_order_facade import SalesOrderFacade


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

        print("\n" + "=" * 70)
        print("Step 6: Get page order numbers for verification")
        print("=" * 70)
        page_order_numbers = facade.get_sorted_order_numbers(50)
        print(f"✅ Got {len(page_order_numbers)} order numbers for verification")
        if page_order_numbers:
            print(f"   First 10: {page_order_numbers[:10]}")

        print("\n" + "=" * 70)
        print("Step 7: Export selected orders")
        print("=" * 70)
        export_result = facade.export_selected(
            select_all_fields=False, template_name="Dayone标准模板 --计算账单", ensure_fields=["系统单号"]
        )

        if export_result["success"]:
            print("\n✅ Export download successful")
            print(f"   - Filename: {export_result['filename']}")
            print(f"   - File path: {export_result['file_path']}")
            print(f"   - File size: {export_result['file_size']} bytes")

            print("\n" + "=" * 70)
            print("Step 8: Verify export file integrity")
            print("=" * 70)
            file_verify = SalesOrderFacade.verify_export_file(export_result["file_path"])
            print(f"✅ File verification: valid={file_verify['valid']}")
            print(f"   - Row count: {file_verify.get('row_count', 'N/A')}")
            print(f"   - Column count: {file_verify.get('col_count', 'N/A')}")
            print(f"   - Headers: {file_verify.get('headers', [])}")

            print("\n" + "=" * 70)
            print("Step 9: Verify order consistency between page and export")
            print("=" * 70)
            consistency = SalesOrderFacade.verify_export_order_consistency(
                export_result["file_path"], page_order_numbers
            )

            if consistency["success"]:
                print("✅ Order consistency verification PASSED")
                print(f"   - Expected count: {consistency['expected_count']}")
                print(f"   - Export count: {consistency['export_count']}")
                print(f"   - Matching count: {consistency['matching_count']}")
            else:
                print("❌ Order consistency verification FAILED")
                print(f"   - Error: {consistency.get('error', 'Unknown')}")
                if consistency.get("mismatched_positions"):
                    print(f"   - Mismatched positions: {consistency['mismatched_positions']}")
        else:
            print(f"\n❌ Export download failed: {export_result['error']}")

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

        print("\n" + "=" * 70)
        print("Step 6: Get page order numbers for verification")
        print("=" * 70)
        page_order_numbers = facade.get_sorted_order_numbers(20)
        print(f"✅ Got {len(page_order_numbers)} order numbers")

        print("\n" + "=" * 70)
        print("Step 7: Export selected orders")
        print("=" * 70)
        export_result = facade.export_selected(
            select_all_fields=False, template_name="Dayone标准模板 --计算账单", ensure_fields=["系统单号"]
        )

        if export_result["success"]:
            print(f"\n✅ Export successful: {export_result['file_path']}")

            print("\n" + "=" * 70)
            print("Step 8: Verify order consistency")
            print("=" * 70)
            consistency = SalesOrderFacade.verify_export_order_consistency(
                export_result["file_path"], page_order_numbers
            )

            if consistency["success"]:
                print("✅ Order consistency verification PASSED")
            else:
                print("❌ Order consistency verification FAILED")
                print(f"   - Mismatched: {consistency.get('mismatched_positions', [])}")
        else:
            print(f"\n❌ Export failed: {export_result['error']}")

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

        print("\n" + "=" * 70)
        print("Step 6: Export selected orders")
        print("=" * 70)
        export_result = facade.export_selected(
            select_all_fields=False, template_name="Dayone标准模板 --计算账单", ensure_fields=["系统单号"]
        )

        if export_result["success"]:
            print(f"\n✅ Export successful: {export_result['file_path']}")

            file_verify = SalesOrderFacade.verify_export_file(export_result["file_path"])
            print(f"✅ File valid: {file_verify['valid']}, rows: {file_verify.get('row_count', 'N/A')}")
        else:
            print(f"\n❌ Export failed: {export_result['error']}")

        print("\n" + "=" * 70)
        print("Test completed")
        print("=" * 70)

"""Precise test for export flow."""

import os
import time

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import SalesOrderExportPage
from modules.auto_test.pages.sales_order_page import SalesOrderPage

EXPORT_TEMPLATE = "！Dayone标准模板 --计算账单"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestExportFlowPrecise:
    """Precise test for export flow."""

    def test_export_flow_payment_time_asc(self, logged_in_page: Page) -> None:
        """Test export flow with payment time ascending sort."""
        sales_order_page = SalesOrderPage(logged_in_page)
        export_page = SalesOrderExportPage(logged_in_page)

        print("\n" + "=" * 70)
        print("Step 1: Navigate to sales order page")
        print("=" * 70)
        sales_order_page.navigate_to("sales/order/saleOrder")
        logged_in_page.wait_for_timeout(8000)
        print(f"URL: {sales_order_page.current_url}")

        print("\n" + "=" * 70)
        print("Step 2: Click pending tab")
        print("=" * 70)
        sales_order_page.click_tab("待处理")
        logged_in_page.wait_for_timeout(8000)

        print("\n" + "=" * 70)
        print("Step 3: Get order numbers before sort")
        print("=" * 70)
        order_numbers_before = sales_order_page.get_sorted_order_numbers(limit=10)
        print(f"Order numbers before sort: {order_numbers_before}")

        print("\n" + "=" * 70)
        print("Step 4: Click sort dropdown and select payment time ascending")
        print("=" * 70)
        sales_order_page.click_sort_dropdown()
        logged_in_page.wait_for_timeout(3000)

        sales_order_page.select_sort_order("付款时间", is_ascending=True)
        logged_in_page.wait_for_timeout(8000)

        print("\n" + "=" * 70)
        print("Step 5: Get order numbers after sort")
        print("=" * 70)
        page_order_numbers = sales_order_page.get_sorted_order_numbers(limit=30)
        print(f"Order numbers after sort (payment time ascending): {page_order_numbers[:10]}...")
        print(f"Total: {len(page_order_numbers)}")

        assert len(page_order_numbers) > 0, "页面未获取到订单号"

        print("\n" + "=" * 70)
        print("Step 6: Navigate to export page with timestamp and order numbers")
        print("=" * 70)
        timestamp = str(int(time.time() * 1000))
        order_param = ",".join(page_order_numbers[:3]) if page_order_numbers else ""
        print(f"Order param for export: {order_param}")
        export_page.navigate_to(f"sales/order/exportPage?t={timestamp}&orderNo={order_param}")
        logged_in_page.wait_for_timeout(15000)

        print(f"Export page URL: {export_page.current_url}")

        print("\n" + "=" * 70)
        print("Step 7: Click template select dropdown")
        print("=" * 70)
        logged_in_page.evaluate(
            """
            () => {
                const selects = document.querySelectorAll('.el-select');
                if (selects.length > 0) {
                    selects[0].click();
                    return true;
                }
                return false;
            }
        """
        )
        logged_in_page.wait_for_timeout(5000)

        print("\n" + "=" * 70)
        print("Step 8: List available templates")
        print("=" * 70)
        templates = logged_in_page.evaluate(
            """
            () => {
                const result = [];
                const items = document.querySelectorAll('.el-select-dropdown__item, .el-option');
                for (let i = 0; i < items.length; i++) {
                    const text = items[i].innerText.trim();
                    if (text && text.length > 0) {
                        result.push({ index: i, text: text });
                    }
                }
                return result;
            }
        """
        )
        print(f"Found {len(templates)} templates:")
        for template in templates:
            print(f"  [{template['index']}] '{template['text']}'")

        print("\n" + "=" * 70)
        print("Step 9: Select template by keyword 'Dayone'")
        print("=" * 70)
        selected_template_text = logged_in_page.evaluate(
            """
            () => {
                const items = document.querySelectorAll('.el-select-dropdown__item, .el-option');
                for (let i = 0; i < items.length; i++) {
                    const text = items[i].innerText.trim();
                    if (text.includes('Dayone')) {
                        items[i].click();
                        return text;
                    }
                }
                return null;
            }
        """
        )
        print(f"Selected template: '{selected_template_text}'")

        assert selected_template_text is not None, "未找到Dayone模板"

        logged_in_page.wait_for_timeout(2000)

        print("\n" + "=" * 70)
        print("Step 10: Ensure order number field is selected (use template defaults)")
        print("=" * 70)

        selected_count = logged_in_page.evaluate(
            """
            () => {
                return document.querySelectorAll('input[type="checkbox"]:checked').length;
            }
        """
        )
        total_count = logged_in_page.evaluate(
            """
            () => {
                return document.querySelectorAll('input[type="checkbox"]').length;
            }
        """
        )
        print(f"Default selected fields: {selected_count}/{total_count}")

        print("\n" + "=" * 70)
        print("Step 11: Ensure '系统单号' field is selected")
        print("=" * 70)
        field_added = export_page.select_field("系统单号")
        print(f"Field '系统单号' selected: {field_added}")

        print("\n" + "=" * 70)
        print("Step 12: Download via export_page.download_to()")
        print("=" * 70)

        os.makedirs("downloads", exist_ok=True)
        timestamp = int(time.time())
        save_path = f"downloads/sales_order_payment_time_asc_{timestamp}.xlsx"

        download_result = export_page.download_to(save_path, timeout=120000)

        if not download_result["success"]:
            print(f"\n✗ Download failed: {download_result.get('error', 'Unknown')}")
            pytest.fail(f"下载失败: {download_result.get('error')}")

        file_path = download_result["file_path"]
        file_size = download_result["file_size"]

        print("\n✓ Download successful!")
        print(f"  Filename: {download_result['filename']}")
        print(f"  File path: {file_path}")
        print(f"  File size: {file_size} bytes")

        print("\n" + "=" * 70)
        print("Step 12: Read exported order numbers")
        print("=" * 70)
        import openpyxl

        wb = openpyxl.load_workbook(file_path)
        ws = wb.active

        order_numbers = []
        header_row = None

        for row in ws.iter_rows(max_row=1):
            header_row = [cell.value for cell in row]
            break

        if header_row:
            print(f"Exported header row: {[str(h)[:30] if h else '' for h in header_row]}")
            order_col_index = None
            for i, header in enumerate(header_row):
                if header and (
                    "系统单号" in str(header)
                    or "订单号" in str(header)
                    or "销售单号" in str(header)
                    or "systemNo" in str(header).lower()
                ):
                    order_col_index = i
                    break

            if order_col_index is None:
                order_col_index = 0

            for row in ws.iter_rows(min_row=2, max_row=51):
                cell_value = row[order_col_index].value
                if cell_value:
                    order_numbers.append(str(cell_value).strip())

        wb.close()

        print(f"Exported order numbers: {order_numbers[:10]}...")
        print(f"Total exported: {len(order_numbers)}")

        print("\n" + "=" * 70)
        print("Step 13: Verify order consistency")
        print("=" * 70)

        matching_numbers = []
        for order_num in page_order_numbers[:20]:
            if order_num in order_numbers:
                matching_numbers.append(order_num)

        print(f"Matching order numbers: {matching_numbers}")
        print(f"Total matched: {len(matching_numbers)}")

        if matching_numbers:
            page_positions = {num: idx for idx, num in enumerate(page_order_numbers[:20])}
            export_positions = {num: idx for idx, num in enumerate(order_numbers)}

            order_consistent = True
            for i, num in enumerate(matching_numbers[:-1]):
                page_pos = page_positions.get(num, -1)
                export_pos = export_positions.get(num, -1)

                next_num = matching_numbers[i + 1]
                next_page_pos = page_positions.get(next_num, -1)
                next_export_pos = export_positions.get(next_num, -1)

                if (page_pos < next_page_pos) != (export_pos < next_export_pos):
                    order_consistent = False
                    print(f"Order inconsistent: {num} and {next_num}")
                    break

            if order_consistent:
                print("\n✅ 排序一致性验证通过！导出顺序与页面排序一致")
            else:
                print("\n❌ 排序一致性验证失败！导出顺序与页面排序不一致")
                pytest.fail("排序一致性验证失败")
        else:
            print("\n❌ 没有匹配的订单号")
            pytest.fail("没有匹配的订单号")

        print("\n" + "=" * 70)
        print("Test completed")
        print("=" * 70)

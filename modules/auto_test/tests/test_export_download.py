"""Test export download functionality."""

import time
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import SalesOrderExportPage
from modules.auto_test.pages.sales_order_page import SalesOrderPage



@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestExportDownload:
    """Test export download functionality."""

    def test_export_download_simple(self, logged_in_page: Page) -> None:
        """Test simple export download."""
        export_page = SalesOrderExportPage(logged_in_page)
        sales_order_page = SalesOrderPage(logged_in_page)

        print("\n=== Step 1: Navigate to export page ===")
        sales_order_page.navigate_to("sales/order/saleOrder")
        logged_in_page.wait_for_load_state("networkidle")
        order_numbers = sales_order_page.get_sorted_order_numbers(limit=1)
        assert order_numbers, "测试环境没有可用于导出的订单"
        timestamp = str(int(time.time() * 1000))
        export_page.navigate_to(
            f"sales/order/exportPage?t={timestamp}&orderNo={order_numbers[0]}"
        )
        assert export_page.wait_for_export_page(timeout=30000), "导出页面未完成加载"

        print(f"URL: {export_page.current_url}")

        print("\n=== Step 2: Check export page structure ===")
        page_html = logged_in_page.evaluate(
            """
            () => {
                return document.body.innerHTML.substring(0, 5000);
            }
        """
        )
        print("Page HTML snippet (first 5000 chars):")
        print(page_html[:2000])

        print("\n=== Step 3: Check all buttons ===")
        buttons = logged_in_page.evaluate(
            """
            () => {
                const result = [];
                const btns = document.querySelectorAll('button');
                for (let i = 0; i < btns.length; i++) {
                    const text = btns[i].innerText.trim();
                    if (text) {
                        result.push({
                            index: i,
                            text: text,
                            className: btns[i].className,
                            id: btns[i].id || ''
                        });
                    }
                }
                return result;
            }
        """
        )
        print(f"Found {len(buttons)} buttons:")
        for btn in buttons:
            print(f"  [{btn['index']}] text='{btn['text']}', class={btn['className']}, id={btn['id']}")

        print("\n=== Step 4: Select the first available export template ===")
        selects = logged_in_page.locator(".el-select")
        assert selects.count() > 0, "未找到导出模板选择器"
        selects.first.click()
        options = logged_in_page.locator(".el-select-dropdown__item:visible, .el-option:visible")
        options.first.wait_for(state="visible", timeout=30000)
        assert options.count() > 0, "测试环境未返回可用导出模板"
        options.first.click()

        print("\n=== Step 5: Wait for download (the page object performs one click) ===")
        result = export_page.wait_for_download(timeout=120000)
        assert result["success"], result.get("error", "download failed")
        assert result["file_size"] > 0, "下载文件为空"
        filename = result["filename"]
        file_path = result["file_path"]
        file_size = result["file_size"]

        print("\n✓ Download successful!")
        print(f"  Filename: {filename}")
        print(f"  File path: {file_path}")
        print(f"  File size: {file_size} bytes")

        print("\n=== Test completed ===")

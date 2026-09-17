"""Simple sales order export smoke test."""

import time

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import EXPORT_TEMPLATE, SalesOrderExportPage
from modules.auto_test.pages.sales_order_page import SalesOrderPage


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
@pytest.mark.smoke
class TestSalesExportSimple:
    """Smoke coverage for exporting selected sales orders on the current page."""

    def test_simple_export(self, logged_in_page: Page) -> None:
        """Export selected current-page sales orders and verify a file is produced."""
        sales_order_page = SalesOrderPage(logged_in_page)
        export_page = SalesOrderExportPage(logged_in_page)

        sales_order_page.navigate_to("sales/order/saleOrder")
        sales_order_page.wait_for_order_page_ready(timeout=60000)

        # The seeded CI order fixture is visible in the all-orders view.  The
        # previous pending-only assumption made this test account-dependent.
        sales_order_page.click_tab("全部订单")
        data_state = sales_order_page.wait_for_order_data_state(timeout=60000)
        if data_state == "timeout":
            pytest.fail("销售订单页控件已就绪，但订单列表未明确进入有数据或无数据状态")
        if data_state == "empty":
            pytest.skip("当前销售订单查询结果为空，跳过依赖业务数据的导出冒烟")

        order_numbers = sales_order_page.get_sorted_order_numbers(limit=10)
        assert order_numbers, "页面未获取到可导出的订单号"

        sales_order_page.select_all_current_page()
        selected_count = sales_order_page.get_selected_count()
        assert selected_count > 0, "当前页未成功勾选可导出的订单"

        sales_order_page.select_export_selected()
        logged_in_page.wait_for_load_state("networkidle")

        assert "sales/order/exportPage" in export_page.get_current_url()
        assert "orderNo=" in export_page.get_current_url(), "导出页 URL 未携带订单号参数"

        template_selected = export_page.select_export_template(EXPORT_TEMPLATE)
        assert template_selected, f"未成功选择导出模板: {EXPORT_TEMPLATE}"

        export_page.select_field("系统单号")

        save_path = f".runtime/downloads/sales_order_simple_{int(time.time())}.xlsx"
        download_result = export_page.download_to(save_path, timeout=120000)

        assert download_result["success"], f"Download failed: {download_result.get('error')}"
        assert download_result["file_size"] > 0, "导出文件为空"

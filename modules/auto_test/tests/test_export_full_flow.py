"""Full export flow test for sales orders."""

import time
from urllib.parse import quote

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import EXPORT_TEMPLATE, SalesOrderExportPage
from modules.auto_test.pages.sales_order_page import SalesOrderPage


@pytest.mark.regression
@pytest.mark.ui
class TestExportFullFlow:
    def test_export_full_flow(self, logged_in_page: Page) -> None:
        """Test the full export flow."""
        sales_order_page = SalesOrderPage(logged_in_page)
        export_page = SalesOrderExportPage(logged_in_page)

        sales_order_page.navigate_to("sales/order/saleOrder")
        sales_order_page.wait_for_order_page_ready(timeout=60000)
        try:
            sales_order_page.click_tab("待处理")
        except Exception as exc:
            pytest.fail(f"无法切换到待处理标签: {type(exc).__name__}")

        data_state = sales_order_page.wait_for_order_data_state(timeout=60000)
        if data_state == "timeout":
            pytest.fail("销售订单页控件已就绪，但订单列表未明确进入有数据或无数据状态")
        if data_state == "empty":
            pytest.skip("当前待处理销售订单查询结果为空，跳过依赖业务数据的导出全流程")

        order_numbers = []
        for attempt in range(3):
            order_numbers = sales_order_page.get_sorted_order_numbers(limit=20)
            if order_numbers:
                break
            print(f"\n⚠️ 第 {attempt + 1}/3 次未获取到订单号，等待订单列表刷新")
            data_state = sales_order_page.wait_for_order_data_state(timeout=30000)
            if data_state == "empty":
                pytest.skip("订单列表刷新后变为空，跳过依赖业务数据的导出全流程")
            if data_state == "timeout":
                pytest.fail("订单列表刷新超时，未能确认页面状态")

        if not order_numbers:
            pytest.skip("当前销售订单页没有可用于实时导出的订单，跳过依赖 UAT 数据的导出全流程")

        order_param = quote(",".join(order_numbers))
        export_page.navigate_to(f"sales/order/exportPage?t={int(time.time() * 1000)}&orderNo={order_param}")
        assert export_page.wait_for_export_page(), "Export page failed to load: " f"{export_page.last_wait_diagnostics}"
        logged_in_page.locator(".el-select:visible").first.wait_for(state="visible", timeout=30000)

        print("\n✅ 已导航到同源导出页面")

        template_selected = export_page.select_export_template(EXPORT_TEMPLATE)
        print(f"\n模板选择结果: {template_selected}")
        assert template_selected, f"未成功选择模板: {EXPORT_TEMPLATE}"
        print(f"\n✅ 已选择导出模板: {EXPORT_TEMPLATE}")

        export_page.select_all_fields(fast_mode=True)
        print("\n✅ 已选择所有导出字段")

        download_result = export_page.wait_for_download(timeout=120000)

        if download_result["success"]:
            print("\n✅ 导出下载成功")
            print(f"   - 文件名: {download_result['filename']}")
            print(f"   - 文件路径: {download_result['file_path']}")
            print(f"   - 文件大小: {download_result['file_size']}字节 ({download_result['file_size']/1024:.2f}KB)")
        else:
            print(f"\n⚠️ 导出下载失败: {download_result['error']}")
            pytest.fail(f"导出下载失败: {download_result['error']}")

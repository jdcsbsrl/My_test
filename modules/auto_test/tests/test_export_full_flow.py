"""Full export flow test for sales orders."""

import time

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import SalesOrderExportPage

EXPORT_TEMPLATE = "！Dayone标准模板 --计算账单"


class TestExportFullFlow:
    def test_export_full_flow(self, logged_in_page: Page) -> None:
        """Test the full export flow."""
        export_page = SalesOrderExportPage(logged_in_page)

        timestamp = str(int(time.time() * 1000))
        export_page.navigate_to(f"sales/order/exportPage?t={timestamp}&orderNo=")
        logged_in_page.wait_for_timeout(15000)

        print(f"\n✅ 已导航到导出页面: {export_page.get_current_url()}")

        template_selected = export_page.select_export_template(EXPORT_TEMPLATE)
        print(f"\n模板选择结果: {template_selected}")
        assert template_selected, f"未成功选择模板: {EXPORT_TEMPLATE}"
        print(f"\n✅ 已选择导出模板: {EXPORT_TEMPLATE}")

        export_page.select_all_fields()
        print("\n✅ 已选择所有导出字段")

        download_result = export_page.wait_for_download(timeout=300000)

        if download_result["success"]:
            print("\n✅ 导出下载成功")
            print(f"   - 文件名: {download_result['filename']}")
            print(f"   - 文件路径: {download_result['file_path']}")
            print(f"   - 文件大小: {download_result['file_size']}字节 ({download_result['file_size']/1024:.2f}KB)")
        else:
            print(f"\n⚠️ 导出下载失败: {download_result['error']}")
            pytest.fail(f"导出下载失败: {download_result['error']}")

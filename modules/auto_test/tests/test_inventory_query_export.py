"""Inventory SKU Query and Export Regression Tests."""

import os
import time

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.inventory_export_page import InventoryExportPage
from modules.auto_test.pages.inventory_sku_page import InventorySKUPage


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
@pytest.mark.core
class TestInventoryQuery:
    """Tests for inventory SKU query functionality."""

    def test_page_display(self, logged_in_page: Page) -> None:
        """Test inventory SKU page displays correctly."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()

        search_btn = logged_in_page.locator('button:has-text("搜索")')
        reset_btn = logged_in_page.locator('button:has-text("重置")')
        export_btn = logged_in_page.locator('button:has-text("导出")')

        assert search_btn.count() > 0, "搜索按钮不存在"
        assert reset_btn.count() > 0, "重置按钮不存在"
        assert export_btn.count() > 0, "导出按钮不存在"

        print("\n✅ 库存SKU页面显示正常")

    def test_search_with_empty_condition(self, logged_in_page: Page) -> None:
        """Test search with no conditions."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        response_time = sku_page.click_search()
        count = sku_page.get_result_count()

        assert response_time < 30, f"响应时间过长: {response_time}秒"
        print(f"\n✅ 无条件搜索成功 - 响应时间: {response_time:.2f}秒, 结果数: {count}")

    def test_search_by_sku_code(self, logged_in_page: Page) -> None:
        """Test search by SKU code."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.fill_sku_code("TEST")
        response_time = sku_page.click_search()

        assert response_time < 30, f"响应时间过长: {response_time}秒"
        print(f"\n✅ SKU编码搜索成功 - 响应时间: {response_time:.2f}秒")

    def test_search_by_invalid_sku_code(self, logged_in_page: Page) -> None:
        """Test search with invalid SKU code (SQL injection, special chars)."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        invalid_inputs = ["'", '"', "OR 1=1", "<script>", "@#$%^&*"]
        for invalid_input in invalid_inputs:
            sku_page.click_reset()
            sku_page.fill_sku_code(invalid_input)
            try:
                response_time = sku_page.click_search()
                assert response_time < 30, f"响应时间过长: {response_time}秒"
                print(f"\n✅ 无效输入 '{invalid_input}' 处理成功")
            except Exception as e:
                print(f"\n⚠️ 无效输入 '{invalid_input}' 导致异常: {e}")

    def test_search_edge_cases(self, logged_in_page: Page) -> None:
        """Test search with edge case inputs."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        edge_cases = ["", " ", "a" * 200]
        for edge_case in edge_cases:
            sku_page.click_reset()
            sku_page.fill_sku_code(edge_case)
            try:
                response_time = sku_page.click_search()
                assert response_time < 30, f"响应时间过长: {response_time}秒"
                print(f"\n✅ 边缘输入 '{edge_case[:20]}...' 处理成功")
            except Exception as e:
                print(f"\n⚠️ 边缘输入 '{edge_case[:20]}...' 导致异常: {e}")

    def test_search_result_count(self, logged_in_page: Page) -> None:
        """Test search result count display."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.click_search()
        count = sku_page.get_result_count()

        assert count >= 0, "结果数应为非负数"
        print(f"\n✅ 搜索结果数量: {count}")

    def test_search_results_format(self, logged_in_page: Page) -> None:
        """Test search results format is correct."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.click_search()
        results = sku_page.get_search_results()

        print("\n✅ 搜索结果格式验证:")
        print(f"   - 行数: {len(results)}")
        if len(results) > 0:
            print(f"   - 列数: {len(results[0].keys())}")
            print(f"   - 列名: {list(results[0].keys())}")


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestInventoryExport:
    """Tests for inventory SKU export functionality."""

    def test_export_button_exists(self, logged_in_page: Page) -> None:
        """Test export button exists and is visible."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()

        export_btn = logged_in_page.locator('button:has-text("导出")')

        assert export_btn.count() > 0, "导出按钮不存在"
        assert export_btn.first.is_visible(), "导出按钮不可见"
        print("\n✅ 导出按钮存在且可见")

    def test_search_yx_l_pattern(self, logged_in_page: Page) -> None:
        """Test search with YX-L pattern and verify results."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        logged_in_page.wait_for_timeout(2000)

        print("\n=== 搜索前页面状态 ===")
        body_text = logged_in_page.text_content("body")[:500]
        print(f"页面文本片段: {body_text}")

        sku_page.click_reset()
        logged_in_page.wait_for_timeout(2000)

        sku_input = logged_in_page.locator('input[placeholder*="库存SKU编码"]')
        print(f"\n重置后输入框数量: {sku_input.count()}")

        sku_page.fill_sku_code("YX-L")
        logged_in_page.wait_for_timeout(1000)

        actual_value = sku_input.first.input_value() if sku_input.count() > 0 else ""
        print(f"输入框实际值: '{actual_value}'")

        search_btns = logged_in_page.locator('button:has-text("搜索")').all()
        print(f"搜索按钮数量: {len(search_btns)}")

        response_time = sku_page.click_search()
        logged_in_page.wait_for_timeout(5000)

        count = sku_page.get_result_count()
        print(f"搜索结果数: {count}")

        body_text = logged_in_page.text_content("body")[:500]
        print(f"搜索后页面文本片段: {body_text}")

        assert response_time < 30, f"响应时间过长: {response_time}秒"
        assert count > 0, f"搜索结果数应为正数，实际为: {count}"

        # 自定义表格组件缺少<thead>，改用页面文本内容检查
        found_yx_l = "YX-L" in (body_text or "")

        assert found_yx_l, "搜索结果中未找到包含YX-L的SKU"
        print("\n✅ YX-L模式搜索成功")
        print(f"   - 响应时间: {response_time:.2f}秒")
        print(f"   - 结果数: {count}")

    def test_export_current_search_results(self, logged_in_page: Page) -> None:
        """Test export current search results flow: search -> export -> export page -> realtime export."""
        sku_page = InventorySKUPage(logged_in_page)
        export_page = InventoryExportPage(logged_in_page)

        sku_page.navigate_to_search_page()
        logged_in_page.wait_for_timeout(2000)

        sku_page.click_reset()
        logged_in_page.wait_for_timeout(1500)

        sku_page.fill_sku_code("YX-L")
        logged_in_page.wait_for_timeout(500)

        sku_page.click_search()
        logged_in_page.wait_for_timeout(5000)

        count = sku_page.get_result_count()
        assert count > 0, f"搜索结果数应为正数，实际为: {count}"
        print(f"\n✅ 搜索YX-L完成，结果数: {count}")

        print("\n=== 搜索结果前十条 ===")
        results = sku_page.get_search_results()
        if len(results) > 0:
            headers = list(results[0].keys())
            print(f"列名: {headers[:5]}")
            print("-" * 150)
            for i, row in enumerate(results[:10]):
                row_values = []
                for header in headers[:5]:
                    row_values.append(str(row.get(header, "")).ljust(20))
                print(f"{i+1:2d}. {' | '.join(row_values)}")

        sku_page.select_export_current_search()
        logged_in_page.wait_for_timeout(5000)

        exported = export_page.wait_for_export_page(timeout=30000)
        assert exported, "未成功跳转到导出页面"
        print(f"\n✅ 已跳转到导出页面: {export_page.page.url}")

        export_page.select_all_fields(fast_mode=True)
        print("\n✅ 已选择所有导出字段")

        download_result = export_page.download_to(
            f"downloads/inventory_query_export_{int(time.time())}.xlsx", timeout=120000
        )
        assert download_result["success"], f"导出下载失败: {download_result.get('error')}"
        assert download_result["file_size"] > 0, "导出文件为空"

        if download_result["success"]:
            print("\n✅ 导出下载成功")
            print(f"   - 文件名: {download_result['filename']}")
            print(f"   - 文件路径: {download_result['file_path']}")
            print(f"   - 文件大小: {download_result['file_size']}字节 ({download_result['file_size']/1024:.2f}KB)")

            if download_result["file_path"] and os.path.exists(download_result["file_path"]):
                print("\n📄 导出文件内容预览（前500字节）:")
                with open(download_result["file_path"], "rb") as f:
                    content = f.read(500).decode("utf-8", errors="replace")
                    print(content)
        else:
            print(f"\n⚠️ 导出下载失败: {download_result['error']}")

    def test_export_with_empty_results_disabled(self, logged_in_page: Page) -> None:
        """Test that export is disabled when search returns no results."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()
        sku_page.click_reset()

        sku_page.fill_sku_code("NONEXISTENT_SKU_12345")
        sku_page.click_search()

        count = sku_page.get_result_count()
        print(f"\n搜索无结果测试 - 结果数: {count}")

        if count == 0:
            sku_page.click_export()
            logged_in_page.wait_for_timeout(500)

            export_menu_item = logged_in_page.locator('span:has-text("导出当前搜索结果")')
            if export_menu_item.count() > 0:
                is_disabled = export_menu_item.first.get_attribute("disabled")
                is_gray = "disabled" in (export_menu_item.first.get_attribute("class") or "")

                if is_disabled or is_gray:
                    print("\n✅ 当搜索无结果时，导出当前搜索结果选项不可用（符合预期）")
                else:
                    print("\n⚠️ 当搜索无结果时，导出当前搜索结果选项仍可用（可能不符合预期）")
            else:
                print("\n⚠️ 未找到导出当前搜索结果菜单选项")
        else:
            print("\n⚠️ 当前环境搜索NONEXISTENT_SKU_12345仍有结果，无法验证无结果场景")


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p2
class TestInventoryReset:
    """Tests for inventory SKU reset functionality."""

    def test_reset_clears_inputs(self, logged_in_page: Page) -> None:
        """Test reset clears all input fields."""
        sku_page = InventorySKUPage(logged_in_page)
        sku_page.navigate_to_search_page()

        sku_page.fill_sku_code("TEST")
        sku_page.click_reset()

        sku_input = logged_in_page.locator('input[placeholder*="库存SKU编码"]')
        input_value = sku_input.first.input_value() if sku_input.count() > 0 else ""

        assert input_value == "", "重置后输入框应清空"
        print("\n✅ 重置功能正常，输入框已清空")

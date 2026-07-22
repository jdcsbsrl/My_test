import re
import time

import allure
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class InventorySKUPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.search_url = "product/productCenter/inventoryInfo"

    @allure.step("导航到库存SKU页面")
    def navigate_to_search_page(self) -> None:
        self.navigate_to(self.search_url)
        self.wait_for_load_state()
        self.page.wait_for_timeout(5000)

        menu_selectors = [
            '//span[contains(text(), "产品中心")]',
            '//span[contains(text(), "库存管理")]',
            '//span[contains(text(), "库存SKU")]',
            '//div[contains(@class, "menu")]//span[contains(text(), "库存")]',
            '//a[contains(@href, "inventory")]',
        ]
        for selector in menu_selectors:
            try:
                menu_item = self.page.locator(selector)
                if menu_item.count() > 0 and menu_item.is_visible():
                    menu_item.click()
                    self.wait_for_load_state()
                    self.page.wait_for_timeout(3000)
                    logger.info(f"通过菜单导航到库存页面: {selector}")
                    break
            except Exception:
                continue

        logger.info("导航到库存SKU页面")

    @allure.step("输入SKU编码: {sku_code}")
    def fill_sku_code(self, sku_code: str) -> None:
        selector = 'input[placeholder*="库存SKU编码"]'
        locator = self.page.locator(selector)
        if locator.count() > 0:
            locator.first.clear()
            locator.first.fill(sku_code)
        else:
            logger.warning("未找到SKU编码输入框")

    @allure.step("输入产品名称: {product_name}")
    def fill_product_name(self, product_name: str) -> None:
        selector = 'input[placeholder*="产品名称"]'
        locator = self.page.locator(selector)
        if locator.count() > 0:
            locator.first.clear()
            locator.first.fill(product_name)
        else:
            logger.warning("未找到产品名称输入框")

    @allure.step("选择仓库: {warehouse}")
    def select_warehouse(self, warehouse: str) -> None:
        selector = 'input[placeholder*="选择仓库"]'
        locator = self.page.locator(selector)
        if locator.count() > 0:
            locator.first.click(force=True)
            self.page.wait_for_timeout(500)
            option = self.page.locator(f'.el-select-dropdown__item:has-text("{warehouse}")').first
            if option.count() > 0:
                option.click(force=True)
                logger.info(f"选择仓库: {warehouse}")

    @allure.step("点击搜索按钮")
    def click_search(self) -> float:
        start_time = time.time()
        search_btn = self.page.locator('button:has-text("搜索")')
        search_btn.first.click()
        self.wait_for_load_state()
        self.wait_for_search_results()
        elapsed = time.time() - start_time
        logger.info(f"搜索响应时间: {elapsed:.2f}秒")
        return elapsed

    @allure.step("点击重置按钮")
    def click_reset(self) -> None:
        reset_selectors = [
            'button:has-text("重置")',
            'button:has-text("清除")',
            'button:has-text("清空")',
            '.ant-btn:has-text("重置")',
            '.ant-btn:has-text("清除")',
            '.ant-btn:has-text("清空")',
            '.el-button:has-text("重置")',
            '.el-button:has-text("清除")',
            '.el-button:has-text("清空")',
        ]
        for selector in reset_selectors:
            try:
                reset_btn = self.page.locator(selector)
                if reset_btn.count() > 0:
                    reset_btn.click()
                    self.page.wait_for_timeout(1500)
                    logger.info(f"已重置搜索条件: {selector}")
                    return
            except Exception:
                continue
        logger.warning("未找到重置按钮")

    @allure.step("点击导出按钮")
    def click_export(self) -> None:
        export_btn = self.page.locator('button:has-text("导出")')
        export_btn.first.click()
        logger.info("点击导出按钮")

    @allure.step("选择导出当前搜索的库存SKU")
    def select_export_current_search(self) -> None:
        self.click_export()
        self.page.wait_for_timeout(1000)

        try:
            self.page.evaluate(
                """() => {
                const items = document.querySelectorAll('.el-dropdown-menu__item');
                for (const item of items) {
                    const text = item.textContent || "";
                    if (text.includes("导出当前搜索的库存SKU")) {
                        item.click();
                        return true;
                    }
                }
                return false;
            }"""
            )
            self.page.wait_for_timeout(3000)
            logger.info("选择导出当前搜索的库存SKU")
            return
        except Exception as e:
            logger.warning(f"JS点击导出菜单失败: {e}")

        menu_items = self.page.locator(".el-dropdown-menu__item").all()
        found = False
        for item in menu_items:
            try:
                text = item.text_content() or ""
                if "导出当前搜索的库存SKU" in text:
                    item.click(force=True)
                    self.page.wait_for_timeout(3000)
                    logger.info("选择导出当前搜索的库存SKU")
                    found = True
                    break
            except Exception:
                pass

        if not found:
            export_menu_item = self.page.locator('span:has-text("导出当前搜索的库存SKU")')
            if export_menu_item.count() > 0:
                export_menu_item.first.click(force=True)
                self.page.wait_for_timeout(3000)
                logger.info("选择导出当前搜索的库存SKU")
            else:
                logger.warning("未找到导出当前搜索的库存SKU菜单")

    @allure.step("选择导出勾选的库存SKU")
    def select_export_selected(self) -> None:
        self.click_export()
        self.page.wait_for_timeout(1000)
        menu_items = self.page.locator(".el-dropdown-menu__item").all()
        for item in menu_items:
            try:
                text = item.text_content() or ""
                if "导出勾选的库存SKU" in text:
                    item.click(force=True)
                    logger.info("选择导出勾选的库存SKU")
                    return
            except Exception:
                pass
        raise Exception("未找到'导出勾选的库存SKU'菜单")

    @allure.step("获取搜索结果数量")
    def get_result_count(self) -> int:
        try:
            body_text = self.page.text_content("body") or ""
            patterns = [
                r"共\s*(\d+)\s*条",
                r"共(\d+)条",
                r"共\s*(\d+)",
            ]
            for pattern in patterns:
                match = re.search(pattern, body_text)
                if match:
                    return int(match.group(1))

            rows = self.page.locator("table tbody tr").all()
            if rows:
                return len(rows)

            return 0
        except Exception:
            try:
                rows = self.page.locator("table tbody tr").all()
                return len(rows) if rows else 0
            except Exception:
                return 0

    @allure.step("获取搜索结果列表")
    def get_search_results(self) -> list[dict]:
        results = []
        rows_locator = self.page.locator("table tbody tr")
        count = rows_locator.count()
        headers = self.page.locator("table thead th").all()
        for i in range(count):
            row = rows_locator.nth(i)
            row_data = {}
            cells = row.locator("td")
            cell_count = cells.count()
            for j in range(min(cell_count, len(headers))):
                try:
                    header_text = headers[j].text_content() or f"column_{j}"
                    cell_text = cells.nth(j).text_content() or ""
                    row_data[header_text.strip()] = cell_text.strip()
                except Exception:
                    pass
            results.append(row_data)
        return results

    @allure.step("验证搜索结果包含SKU: {expected_sku}")
    def assert_results_contain_sku(self, expected_sku: str) -> bool:
        results = self.get_search_results()
        found = any(expected_sku.lower() in str(row.values()).lower() for row in results)
        return found

    @allure.step("验证搜索结果数量大于0")
    def assert_has_results(self) -> bool:
        count = self.get_result_count()
        return count > 0

    @allure.step("验证搜索结果数量为0")
    def assert_no_results(self) -> bool:
        count = self.get_result_count()
        return count == 0

    @allure.step("等待搜索结果加载")
    def wait_for_search_results(self, timeout: int = 30000) -> None:
        table_selectors = [
            "table.ant-table-table",
            "table.el-table__body",
            ".ant-table-table",
            ".el-table__body-wrapper",
            "table",
            "div[class*='table']",
        ]
        for selector in table_selectors:
            try:
                self.page.wait_for_selector(selector, timeout=timeout // len(table_selectors))
                logger.info(f"找到表格元素: {selector}")
                self.wait_for_load_state()
                return
            except Exception:
                continue
        logger.warning("未找到表格元素")

    @allure.step("全选当前页所有记录")
    def select_all_current_page(self) -> None:
        """点击表头全选复选框"""
        try:
            self.page.evaluate(
                """() => {
                const checkbox = document.querySelector('thead input[type="checkbox"]');
                if (checkbox && !checkbox.checked) {
                    checkbox.click();
                }
            }"""
            )
            self.page.wait_for_timeout(1000)
            logger.info("已全选当前页")
        except Exception as e:
            logger.warning(f"JS全选失败: {e}")
            checkbox = self.page.locator("thead .el-checkbox__input").first
            checkbox.click(force=True)
            self.page.wait_for_timeout(1000)

    @allure.step("取消全选")
    def deselect_all(self) -> None:
        try:
            self.page.evaluate(
                """() => {
                const checkbox = document.querySelector('thead input[type="checkbox"]');
                if (checkbox && checkbox.checked) {
                    checkbox.click();
                }
            }"""
            )
            self.page.wait_for_timeout(1000)
            logger.info("已取消全选")
        except Exception as e:
            logger.warning(f"JS取消全选失败: {e}")

    @allure.step("选择单行: {row_index}")
    def select_row(self, row_index: int) -> None:
        """选择指定行（从1开始）"""
        try:
            self.page.evaluate(
                f"""() => {{
                const rows = document.querySelectorAll('table tbody tr');
                if (rows.length >= {row_index}) {{
                    const row = rows[{row_index - 1}];
                    const checkbox = row.querySelector('input[type="checkbox"]');
                    if (checkbox && !checkbox.checked) {{
                        checkbox.click();
                    }}
                }}
            }}"""
            )
            self.page.wait_for_timeout(500)
            logger.info(f"已选择第{row_index}行")
        except Exception as e:
            logger.warning(f"选择行失败: {e}")

    @allure.step("获取已选中的行数")
    def get_selected_count(self) -> int:
        try:
            count = self.page.evaluate(
                """() => {
                const checked = document.querySelectorAll('table tbody input[type="checkbox"]:checked');
                return checked.length;
            }"""
            )
            return count or 0
        except Exception:
            return 0

    @allure.step("检查表头全选复选框是否被勾选")
    def is_header_checkbox_checked(self) -> bool:
        try:
            checked = self.page.evaluate(
                """() => {
                const checkbox = document.querySelector('thead input[type="checkbox"]');
                return checkbox ? checkbox.checked : false;
            }"""
            )
            return bool(checked)
        except Exception:
            return False

    @allure.step("设置每页显示数量: {page_size}")
    def set_page_size(self, page_size: int) -> float:
        """设置分页大小"""
        start_time = time.time()
        try:
            self.page.evaluate(
                f"""() => {{
                const select = document.querySelector('.el-pagination .el-select');
                if (select) {{
                    select.click();
                    setTimeout(() => {{
                        const options = document.querySelectorAll('.el-select-dropdown__item');
                        for (const opt of options) {{
                            if (opt.textContent.trim() === '{page_size}' ||
                                opt.textContent.trim() === '{page_size}/页') {{
                                opt.click();
                                break;
                            }}
                        }}
                    }}, 300);
                }}
            }}"""
            )
            self.page.wait_for_timeout(3000)
            elapsed = time.time() - start_time
            logger.info(f"设置分页{page_size}/页，耗时{elapsed:.2f}秒")
            return elapsed
        except Exception as e:
            logger.warning(f"设置分页大小失败: {e}")
            return 0.0

    @allure.step("跳转到第{page_num}页")
    def goto_page(self, page_num: int) -> None:
        """跳转到指定页码"""
        try:
            page_input = self.page.locator(".el-pagination .el-pagination__jump input").first
            if page_input.count() > 0:
                page_input.fill(str(page_num))
                page_input.press("Enter")
                self.page.wait_for_timeout(2000)
                logger.info(f"跳转到第{page_num}页")
        except Exception as e:
            logger.warning(f"跳转页码失败: {e}")

    @allure.step("点击下一页")
    def click_next_page(self) -> None:
        try:
            next_btn = self.page.locator(".el-pagination .btn-next").first
            if next_btn.count() > 0:
                next_btn.click(force=True)
                self.page.wait_for_timeout(2000)
        except Exception as e:
            logger.warning(f"点击下一页失败: {e}")

    @allure.step("获取当前页码")
    def get_current_page(self) -> int:
        try:
            text = self.page.evaluate(
                """() => {
                const active = document.querySelector('.el-pagination .active');
                return active ? active.textContent.trim() : '';
            }"""
            )
            return int(text) if text and text.isdigit() else 1
        except Exception:
            return 1

    @allure.step("获取总页数")
    def get_total_pages(self) -> int:
        try:
            text = self.page.evaluate(
                """() => {
                const pagination = document.querySelector('.el-pagination');
                if (pagination) {
                    const total = pagination.querySelector('.el-pagination__total');
                    if (total) return total.textContent.trim();
                }
                return '';
            }"""
            )
            if text:
                m = re.search(r"共\s*(\d+)\s*条", text)
                if m:
                    total_count = int(m.group(1))
                    return (total_count + 9) // 10
            return 1
        except Exception:
            return 1

    @allure.step("获取当前页实际行数")
    def get_current_page_row_count(self) -> int:
        return self.page.locator("table tbody tr").count()

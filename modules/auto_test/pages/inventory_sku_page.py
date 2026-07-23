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
        self.wait_for_load_state("domcontentloaded")
        self.page.locator("input, button, table, [role='table']").first.wait_for(state="attached", timeout=30000)
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
        search_btn = self.page.locator('button:visible:has-text("搜索")')
        if search_btn.count() == 0:
            raise ValueError("未找到可见的搜索按钮")
        search_btn.first.click(timeout=10000)
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
                    self._wait_for_loading_finished()
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
            if self._has_empty_state():
                return 0

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

    def _has_empty_state(self) -> bool:
        """Return True when the current table explicitly shows an empty result state."""
        empty_locator = self.page.locator(
            ".el-table__empty-block:visible, .el-table__empty-text:visible, "
            ".ant-empty:visible, .ant-table-placeholder:visible, [class*='empty']:visible"
        )
        try:
            for i in range(empty_locator.count()):
                text = (empty_locator.nth(i).text_content(timeout=1000) or "").strip()
                if not text:
                    continue
                if any(keyword in text for keyword in ("暂无数据", "无数据", "没有数据", "No Data", "No data")):
                    return True
        except Exception:
            return False
        return False

    def _wait_for_loading_finished(self, timeout: int = 30000) -> None:
        """Wait for common table loading masks to disappear."""
        try:
            self.page.locator(".el-loading-mask:visible, .ant-spin-spinning:visible").first.wait_for(
                state="hidden", timeout=timeout
            )
        except Exception:
            pass

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
        try:
            self._wait_for_loading_finished(timeout)
            self.page.locator(
                ".virtual-pro-table:visible, table:visible, [role='table']:visible, .el-table:visible, .ant-table:visible, "
                ".el-table__empty-block:visible, .ant-empty:visible, [class*='empty']:visible"
            ).first.wait_for(state="visible", timeout=timeout)
        except Exception as exc:
            raise TimeoutError(f"库存SKU结果在 {timeout / 1000:.0f} 秒内未完成刷新") from exc

    @allure.step("全选当前页所有记录")
    def select_all_current_page(self) -> None:
        """通过真实表头复选框全选，并等待选中状态落地。"""
        checkbox = self.page.locator(
            ".el-table__header-wrapper .el-checkbox, .ant-table-thead input[type='checkbox'], "
            "thead input[type='checkbox'], thead .el-checkbox__input"
        ).first
        if checkbox.count() == 0:
            clicked = self.page.evaluate(
                """
                () => {
                    const candidates = [
                        ...document.querySelectorAll('thead input[type="checkbox"]'),
                        ...document.querySelectorAll('thead .el-checkbox, thead .el-checkbox__input'),
                        ...document.querySelectorAll('.el-table__header-wrapper .el-checkbox, .ant-table-thead input[type="checkbox"]'),
                        ...document.querySelectorAll('.vxe-table--header-wrapper input[type="checkbox"], .vxe-header--column .vxe-checkbox--icon')
                    ].filter(el => el.offsetParent !== null);
                    const target = candidates[0];
                    if (!target) return false;
                    target.click();
                    return true;
                }
                """
            )
            if not clicked:
                raise ValueError("未找到表头全选复选框")
        else:
            checkbox.click(force=True, timeout=10000)
        try:
            self.page.wait_for_function(
                """() => document.querySelectorAll(
                    '.el-table__body-wrapper .el-checkbox__input.is-checked, '
                    + '.ant-table-tbody input[type="checkbox"]:checked, '
                    + '.vxe-body--row.is--checked, .vxe-body--row.row--checked'
                ).length > 0""",
                timeout=10000,
            )
        except Exception as exc:
            raise TimeoutError("点击全选后未检测到选中行") from exc
        logger.info("已全选当前页")

    @allure.step("取消全选")
    def deselect_all(self) -> None:
        if self.get_selected_count() == 0:
            return
        checkbox = self.page.locator(
            ".el-table__header-wrapper .el-checkbox, .ant-table-thead input[type='checkbox']"
        ).first
        if checkbox.count() == 0:
            raise ValueError("未找到表头全选复选框")
        checkbox.click(force=True, timeout=10000)
        self.page.wait_for_function(
            """() => document.querySelectorAll(
                '.el-table__body-wrapper .el-checkbox__input.is-checked, '
                + '.ant-table-tbody input[type="checkbox"]:checked'
            ).length === 0""",
            timeout=10000,
        )

    @allure.step("选择单行: {row_index}")
    def select_row(self, row_index: int) -> None:
        """选择指定行（从1开始），使用浏览器真实点击事件。"""
        checkboxes = self.page.locator(
            ".el-table__body-wrapper .el-checkbox, .ant-table-tbody input[type='checkbox']"
        )
        if checkboxes.count() < row_index:
            raise ValueError(f"第 {row_index} 行复选框不存在")
        checkboxes.nth(row_index - 1).click(force=True, timeout=10000)
        try:
            self.page.wait_for_function(
                """expected => document.querySelectorAll(
                    '.el-table__body-wrapper .el-checkbox__input.is-checked, '
                    + '.ant-table-tbody input[type="checkbox"]:checked'
                ).length === expected""",
                arg=1,
                timeout=10000,
            )
        except Exception as exc:
            raise TimeoutError(f"第 {row_index} 行点击后未进入选中状态") from exc

    @allure.step("获取已选中的行数")
    def get_selected_count(self) -> int:
        try:
            return self.page.locator(
                ".el-table__body-wrapper .el-checkbox__input.is-checked, "
                ".ant-table-tbody input[type='checkbox']:checked"
            ).count()
        except Exception:
            return 0

    @allure.step("检查表头全选复选框是否被勾选")
    def is_header_checkbox_checked(self) -> bool:
        try:
            header = self.page.locator(
                ".el-table__header-wrapper .el-checkbox__input.is-checked, "
                ".ant-table-thead input[type='checkbox']:checked"
            )
            return header.count() > 0
        except Exception:
            return False

    @allure.step("设置每页显示数量: {page_size}")
    def set_page_size(self, page_size: int) -> float:
        """通过可见分页控件设置每页数量，并等待表格行数更新。"""
        start_time = time.time()
        size_dropdown = self.page.locator(
            ".el-pagination__sizes .el-select, .ant-pagination-options-size-changer"
        ).first
        if size_dropdown.count() == 0:
            raise ValueError("未找到分页大小选择器")
        size_dropdown.click(timeout=10000)
        if not self._click_page_size_option(page_size):
            available = self._get_page_size_options_text()
            raise ValueError(f"分页选项 {page_size}/页 不存在，可用选项: {available}")
        self.wait_for_search_results()
        self._wait_for_page_size_applied(page_size)
        elapsed = time.time() - start_time
        logger.info(f"设置分页{page_size}/页，耗时{elapsed:.2f}秒")
        return elapsed

    def _click_page_size_option(self, page_size: int) -> bool:
        option_pattern = re.compile(rf"^\s*{page_size}\s*(条\s*/\s*页|/page|/页)?\s*$", re.IGNORECASE)
        option = self.page.locator(
            ".el-select-dropdown__item:visible, .ant-select-item-option:visible"
        ).filter(has_text=option_pattern).first
        if option.count() > 0:
            option.click(timeout=10000)
            return True

        clicked = self.page.evaluate(
            """expected => {
                const nodes = Array.from(document.querySelectorAll(
                    '.el-select-dropdown__item, .ant-select-item-option'
                ));
                const pattern = new RegExp(`^\\s*${expected}\\s*(条\\s*/\\s*页|/page|/页)?\\s*$`, 'i');
                const item = nodes.find(node => pattern.test((node.textContent || '').trim()));
                if (!item) return false;
                item.click();
                return true;
            }""",
            page_size,
        )
        return bool(clicked)

    def _get_page_size_options_text(self) -> list[str]:
        try:
            return self.page.evaluate(
                """() => Array.from(document.querySelectorAll(
                    '.el-select-dropdown__item, .ant-select-item-option'
                )).map(node => (node.textContent || '').trim()).filter(Boolean)"""
            )
        except Exception:
            return []

    def _wait_for_page_size_applied(self, page_size: int) -> None:
        try:
            self.page.wait_for_function(
                """expected => {
                    const sizes = Array.from(document.querySelectorAll(
                        '.el-pagination__sizes input, .el-pagination__sizes .el-input__inner, '
                        + '.ant-pagination-options-size-changer .ant-select-selection-item'
                    ));
                    return sizes.some(node => (node.value || node.textContent || '').includes(String(expected)));
                }""",
                arg=page_size,
                timeout=1000,
            )
        except Exception:
            logger.warning("未检测到分页大小文本更新，继续通过表格行数验证")

    @allure.step("跳转到第{page_num}页")
    def goto_page(self, page_num: int) -> None:
        page_button = self.page.locator(
            f".el-pager li, .ant-pagination-item-{page_num}"
        ).filter(has_text=re.compile(rf"^\s*{page_num}\s*$")).first
        if page_button.count() > 0:
            page_button.click(timeout=10000)
        else:
            page_input = self.page.locator(
                ".el-pagination__jump input, .ant-pagination-options-quick-jumper input"
            ).first
            if page_input.count() == 0:
                raise ValueError(f"未找到第 {page_num} 页按钮或跳页输入框")
            page_input.fill(str(page_num))
            page_input.press("Enter")
        self.page.wait_for_function(
            """expected => {
                const active = document.querySelector('.el-pager li.active, .ant-pagination-item-active');
                return active && Number(active.textContent.trim()) === expected;
            }""",
            arg=page_num,
            timeout=10000,
        )
        self.wait_for_search_results()

    @allure.step("点击下一页")
    def click_next_page(self) -> None:
        current_page = self.get_current_page()
        next_btn = self.page.locator(".el-pagination .btn-next, .ant-pagination-next").first
        if next_btn.count() == 0:
            raise ValueError("未找到下一页按钮")
        next_btn.click(timeout=10000)
        self.page.wait_for_function(
            """previous => {
                const active = document.querySelector('.el-pager li.active, .ant-pagination-item-active');
                return active && Number(active.textContent.trim()) > previous;
            }""",
            arg=current_page,
            timeout=10000,
        )
        self.wait_for_search_results()

    @allure.step("获取当前页码")
    def get_current_page(self) -> int:
        try:
            page = self.page.evaluate(
                """() => {
                // 方法1: Vue pagination internalCurrentPage
                const pagination = document.querySelector('.el-pagination');
                if (pagination && pagination.__vue__) {
                    const vm = pagination.__vue__;
                    if (vm.internalCurrentPage !== undefined) return vm.internalCurrentPage;
                }
                // 方法2: DOM .active
                const active = document.querySelector('.el-pagination .el-pager .active, .el-pagination .active');
                if (active) {
                    const n = parseInt(active.textContent.trim(), 10);
                    if (!isNaN(n)) return n;
                }
                return 1;
            }"""
            )
            return int(page) if page else 1
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

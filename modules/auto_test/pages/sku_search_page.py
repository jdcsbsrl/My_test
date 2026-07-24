import time
import unicodedata

import allure
from playwright.sync_api import Page, expect

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class SKUSearchPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.search_url = "product/productCenter/inventoryInfo"

    @allure.step("导航到SKU搜索页面")
    def navigate_to_search_page(self) -> None:
        self.navigate_to(self.search_url)
        self.wait_for_load_state("domcontentloaded")
        self.page.locator("input, button, table, [role='table']").first.wait_for(state="attached", timeout=30000)
        logger.info("导航到SKU搜索页面")

    @allure.step("设置产品品类: {category}")
    def select_product_category(self, category: str) -> None:
        self._select_dropdown_by_placeholder("产品品类", category)

    @allure.step("设置销售状态: {status}")
    def select_sales_status(self, status: str) -> None:
        self._select_dropdown_by_placeholder("销售状态", status)

    @allure.step("设置产品自定义分类: {custom_category}")
    def select_custom_category(self, custom_category: str) -> None:
        self._select_dropdown_by_placeholder("产品自定义分类", custom_category)

    @allure.step("设置创建人: {creator}")
    def select_creator(self, creator: str) -> None:
        self._select_dropdown_by_placeholder("创建人", creator)

    @allure.step("设置仓库: {warehouse}")
    def select_warehouse(self, warehouse: str) -> None:
        self._select_dropdown_by_placeholder("仓库", warehouse)

    @allure.step("设置运配度: {delivery}")
    def select_delivery_degree(self, delivery: str) -> None:
        self._select_dropdown_by_placeholder("运配度", delivery)

    @allure.step("设置运配仓: {delivery_warehouse}")
    def select_delivery_warehouse(self, delivery_warehouse: str) -> None:
        self._select_dropdown_by_placeholder("运配仓", delivery_warehouse)

    @allure.step("输入SKU编码: {sku_code}")
    def fill_sku_code(self, sku_code: str) -> None:
        self._fill_input_by_placeholder("SKU编码", sku_code)

    @allure.step("输入主SKU: {main_sku}")
    def fill_main_sku(self, main_sku: str) -> None:
        self._fill_input_by_placeholder("主SKU", main_sku)

    @allure.step("输入SKU名称: {sku_name}")
    def fill_sku_name(self, sku_name: str) -> None:
        self._fill_input_by_placeholder("SKU名称", sku_name)

    @allure.step("输入英文名称: {english_name}")
    def fill_english_name(self, english_name: str) -> None:
        self._fill_input_by_placeholder("英文名称", english_name)

    @allure.step("输入原厂SKU: {original_sku}")
    def fill_original_sku(self, original_sku: str) -> None:
        self._fill_input_by_placeholder("原厂SKU", original_sku)

    @allure.step("输入库存数量范围: {begin} - {end}")
    def fill_inventory_quantity_range(self, begin: int, end: int) -> None:
        self._fill_range_input("库存", begin, end)

    @allure.step("输入7天销量范围: {begin} - {end}")
    def fill_sale_seven_range(self, begin: int, end: int) -> None:
        self._fill_range_input("7天销量", begin, end)

    @allure.step("输入库存预警天数范围: {begin} - {end}")
    def fill_warning_days_range(self, begin: int, end: int) -> None:
        self._fill_range_input("库存预警天数", begin, end)

    @allure.step("输入警戒库存范围: {begin} - {end}")
    def fill_warning_qty_range(self, begin: int, end: int) -> None:
        self._fill_range_input("警戒库存", begin, end)

    @allure.step("批量查询 - 输入SKU列表: {sku_list}")
    def batch_query_skus(self, sku_list: list[str]) -> None:
        batch_input_selector = 'textarea[placeholder*="批量查询"], textarea[placeholder*="多个SKU"]'
        sku_text = "\n".join(sku_list)
        self._fill_input(batch_input_selector, sku_text)

    @allure.step("点击高级搜索按钮")
    def click_advanced_search(self) -> None:
        adv_selectors = [
            'button:has-text("高级搜索")',
            "button:has(.icon-filter)",
            '.el-button:has-text("高级搜索")',
            '.ant-btn:has-text("高级搜索")',
        ]
        for selector in adv_selectors:
            try:
                adv_btn = self.page.locator(selector)
                if adv_btn.count() > 0 and adv_btn.is_visible():
                    adv_btn.click()
                    logger.info("已打开高级搜索面板")
                    return
            except Exception:
                continue
        logger.warning("未找到高级搜索按钮")

    @allure.step("点击搜索按钮")
    def click_search(self) -> float:
        start_time = time.time()
        for button_name in ("查询", "搜索"):
            search_btn = self.page.get_by_role("button", name=button_name, exact=True)
            if search_btn.count() > 0 and search_btn.first.is_visible():
                search_btn.first.click(timeout=10000)
                self._wait_for_table_update()
                elapsed = time.time() - start_time
                logger.info(f"搜索响应时间: {elapsed:.2f}秒")
                return elapsed
        raise ValueError("未找到搜索按钮")

    def _wait_for_table_update(self, timeout: int = 30000) -> None:
        """等待搜索表格结束加载，避免 SPA 页面被 networkidle 长连接阻塞。"""
        try:
            self.page.locator(
                ".virtual-pro-table:visible, table:visible, [role='table']:visible, .el-table:visible, .ant-table:visible, "
                ".el-table__empty-block:visible, .ant-empty:visible, [class*='empty']:visible"
            ).first.wait_for(state="visible", timeout=timeout)
        except Exception as exc:
            visible_result_classes = self.page.evaluate(
                """() => Array.from(document.querySelectorAll('[class]'))
                    .filter(e => e.offsetParent !== null && /(table|grid|list|empty)/i.test(e.className))
                    .slice(0, 40).map(e => ({tag: e.tagName, className: e.className, text: e.textContent.trim().slice(0, 80)}))"""
            )
            logger.error("搜索结果容器诊断: {}", visible_result_classes)
            raise TimeoutError(f"搜索结果在 {timeout / 1000:.0f} 秒内未完成刷新") from exc

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
            '//button[contains(text(), "重置")]',
            '//button[contains(text(), "清除")]',
        ]
        for selector in reset_selectors:
            try:
                reset_btn = self.page.locator(selector)
                if reset_btn.count() > 0 and reset_btn.is_visible():
                    reset_btn.click()
                    logger.info(f"已重置搜索条件: {selector}")
                    return
            except Exception:
                continue
        logger.warning("未找到重置按钮")

    @allure.step("点击确定按钮（高级搜索）")
    def click_confirm(self) -> None:
        confirm_selectors = [
            'button:has-text("确定")',
            '.el-button:has-text("确定")',
            '.ant-btn:has-text("确定")',
        ]
        for selector in confirm_selectors:
            try:
                confirm_btn = self.page.locator(selector)
                if confirm_btn.count() > 0 and confirm_btn.is_visible():
                    confirm_btn.click()
                    logger.info("已确认高级搜索条件")
                    return
            except Exception:
                continue
        logger.warning("未找到确定按钮")

    @allure.step("点击取消按钮（高级搜索）")
    def click_cancel(self) -> None:
        cancel_selectors = [
            'button:has-text("取消")',
            '.el-button:has-text("取消")',
            '.ant-btn:has-text("取消")',
        ]
        for selector in cancel_selectors:
            try:
                cancel_btn = self.page.locator(selector)
                if cancel_btn.count() > 0 and cancel_btn.is_visible():
                    cancel_btn.click()
                    logger.info("已取消高级搜索")
                    return
            except Exception:
                continue
        logger.warning("未找到取消按钮")

    @allure.step("获取搜索结果数量")
    def get_result_count(self) -> int:
        try:
            count_selectors = [
                ".ant-pagination-total-text",
                ".el-pagination__total",
                ".pagination-info",
            ]
            for selector in count_selectors:
                count_locator = self.page.locator(selector)
                if count_locator.count() == 0:
                    continue
                count_text = count_locator.first.text_content()
                if count_text:
                    import re

                    match = re.search(r"\d+", count_text)
                    if match:
                        return int(match.group())
            return 0
        except Exception:
            return 0

    @allure.step("获取搜索结果列表")
    def get_search_results(self) -> list[dict[str, str]]:
        results = []
        table_selectors = [
            "table.ant-table-table tbody tr",
            "table.el-table__body tbody tr",
            ".ant-table-body tbody tr",
            ".el-table__body-wrapper tbody tr",
        ]
        for table_selector in table_selectors:
            rows = self.page.locator(table_selector)
            if rows.count() > 0:
                count = rows.count()
                for i in range(count):
                    row = rows.nth(i)
                    row_data = {}
                    cells = row.locator("td")
                    cell_count = cells.count()
                    for j in range(min(cell_count, 10)):
                        header_selectors = [
                            f"table.ant-table-table thead th:nth-child({j+1})",
                            f"table.el-table__body thead th:nth-child({j+1})",
                            f".ant-table-header th:nth-child({j+1})",
                            f".el-table__header th:nth-child({j+1})",
                        ]
                        header_text = f"column_{j}"
                        for hs in header_selectors:
                            ht = self.page.locator(hs).text_content()
                            if ht:
                                header_text = ht
                                break
                        cell_text = cells.nth(j).text_content() or ""
                        row_data[header_text] = cell_text.strip()
                    results.append(row_data)
                return results
        return results

    @allure.step("验证搜索结果包含SKU: {expected_sku}")
    def assert_results_contain_sku(self, expected_sku: str) -> None:
        results = self.get_search_results()
        found = any(expected_sku in str(row.values()) for row in results)
        expect(found).to_be_true()

    @allure.step("验证搜索结果数量大于0")
    def assert_has_results(self) -> None:
        count = self.get_result_count()
        expect(count).to_be_greater_than(0)

    @allure.step("验证搜索结果数量为0")
    def assert_no_results(self) -> None:
        count = self.get_result_count()
        expect(count).to_be(0)

    @allure.step("验证错误提示信息")
    def assert_error_message(self, expected_message: str) -> None:
        error_selectors = [
            ".ant-message-error",
            ".ant-alert-error",
            '[role="alert"]',
            ".el-message--error",
            ".el-alert--error",
        ]
        found = False
        for selector in error_selectors:
            error_locator = self.page.locator(selector)
            if error_locator.count() > 0:
                try:
                    expect(error_locator).to_contain_text(expected_message)
                    found = True
                    break
                except Exception:
                    continue
        if not found:
            logger.warning(f"未找到包含 '{expected_message}' 的错误提示")

    @allure.step("获取页面上的下拉选项")
    def get_dropdown_options(self, placeholder: str) -> list[str]:
        if not self._open_dropdown_by_placeholder(placeholder):
            return []
        try:
            self._wait_for_visible_dropdown_options()
            return self._get_visible_dropdown_options()
        finally:
            self.page.keyboard.press("Escape")

    def get_first_available_dropdown_option(self, placeholder: str, excluded_options: tuple[str, ...] = ("全部",)) -> str:
        """获取指定下拉框中第一个非排除项的真实可用选项。"""
        excluded = {self._normalize_dropdown_option(option) for option in excluded_options}
        options = self.get_dropdown_options(placeholder)
        for option in options:
            normalized_option = self._normalize_dropdown_option(option)
            if normalized_option and normalized_option not in excluded:
                logger.info("动态获取下拉选项: {} -> {}", placeholder, option)
                return option
        raise ValueError(f"下拉选择器“{placeholder}”中未找到非 {excluded_options} 的可用选项，可见选项: {options}")

    def get_first_available_dropdown_option(self, placeholder: str, excluded_options: tuple[str, ...] = ("全部",)) -> str:
        """Get the first usable dropdown option with retries for dynamic dropdowns."""
        excluded = {self._normalize_dropdown_option(option) for option in excluded_options}
        options = []
        for attempt in range(3):
            options = self.get_dropdown_options(placeholder)
            for option in options:
                normalized_option = self._normalize_dropdown_option(option)
                if normalized_option and normalized_option not in excluded:
                    logger.info("鍔ㄦ€佽幏鍙栦笅鎷夐€夐」: {} -> {}", placeholder, option)
                    return option
            logger.warning(
                "Dropdown {} attempt {} has no usable option. Visible options: {}",
                placeholder,
                attempt + 1,
                options,
            )
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(1000)
        raise ValueError(f"Dropdown {placeholder} has no usable option outside {excluded_options}. Visible options: {options}")

    def _dropdown_selectors(self, placeholder: str) -> list[str]:
        return [
            f'.el-form-item:has(.el-form-item__label:has-text("{placeholder}")) .el-select',
            f'.ant-form-item:has(label:has-text("{placeholder}")) .ant-select-selector',
            f'.el-select:has-text("{placeholder}")',
            f'.ant-select:has-text("{placeholder}") .ant-select-selector',
            f'.el-select:has(input[placeholder*="{placeholder}"])',
            f'.ant-select:has(input[placeholder*="{placeholder}"]) .ant-select-selector',
            f'.ant-select-selector:has-text("{placeholder}")',
            f'.el-select:has(.el-input__inner[placeholder*="{placeholder}"]) .el-input__inner',
            f'.ant-select:has(.ant-input[placeholder*="{placeholder}"]) .ant-select-selector',
            f'.ant-select:has(.ant-select-selection-placeholder:has-text("{placeholder}")) .ant-select-selector',
            f'.el-select:has(.el-select__placeholder:has-text("{placeholder}"))',
        ]

    def _open_dropdown_by_placeholder(self, placeholder: str) -> bool:
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(200)
        for selector in self._dropdown_selectors(placeholder):
            try:
                locator = self.page.locator(selector)
                if locator.count() > 0 and locator.first.is_visible():
                    locator.first.click()
                    logger.info(f"点击下拉选择器: {selector}")
                    return True
            except Exception:
                continue
        debug_controls = self.page.evaluate(
            """() => ({
                labels: Array.from(document.querySelectorAll('label')).slice(0, 30).map(e => e.textContent.trim()),
                placeholders: Array.from(document.querySelectorAll('input')).slice(0, 40).map(e => e.placeholder),
                selects: Array.from(document.querySelectorAll('.el-select, .ant-select')).slice(0, 30)
                    .map(e => e.textContent.trim())
            })"""
        )
        logger.error("下拉选择器诊断: {}", debug_controls)
        return False

    def _latest_visible_dropdown(self):
        dropdown_selector = (
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden):visible, "
            ".el-select-dropdown:visible"
        )
        dropdowns = self.page.locator(dropdown_selector)
        count = dropdowns.count()
        if count == 0:
            return None
        return dropdowns.nth(count - 1)

    def _wait_for_visible_dropdown_options(self, timeout: int = 5000) -> None:
        dropdown_selector = (
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden):visible "
            ".ant-select-item-option:visible, "
            ".ant-select-dropdown:not(.ant-select-dropdown-hidden):visible "
            ".ant-select-item-option-content:visible, "
            ".el-select-dropdown:visible .el-select-dropdown__item:visible"
        )
        self.page.locator(dropdown_selector).first.wait_for(state="visible", timeout=timeout)

    def _get_visible_dropdown_options(self) -> list[str]:
        option_selector = (
            ".ant-select-item-option:visible, "
            ".ant-select-item-option-content:visible, "
            ".el-select-dropdown__item:visible"
        )
        dropdown = self._latest_visible_dropdown()
        if dropdown is None:
            return []
        options = dropdown.locator(option_selector)
        result = []
        for index in range(options.count()):
            try:
                text = options.nth(index).inner_text().strip()
                if text and text not in result:
                    result.append(text)
            except Exception:
                continue
        return result

    def _click_visible_dropdown_option(self, value: str) -> bool:
        dropdown = self._latest_visible_dropdown()
        if dropdown is None:
            return False
        option_selectors = [
            f'.ant-select-item-option:has-text("{value}")',
            f'.ant-select-item-option-content:has-text("{value}")',
            f'.el-select-dropdown__item:has-text("{value}")',
            f'//*[contains(text(), "{value}")]',
        ]
        for option_selector in option_selectors:
            try:
                option = dropdown.locator(option_selector)
                if option.count() > 0 and option.first.is_visible():
                    option.first.click()
                    logger.info(f"成功选择选项: {value}")
                    return True
            except Exception:
                continue
        return False

    def _log_dropdown_options_not_found(self, placeholder: str, value: str) -> None:
        try:
            visible_options = self._get_visible_dropdown_options()
        except Exception:
            visible_options = []
        logger.error(
            "下拉选项未找到: placeholder={}, value={}, url={}, visible_options={}",
            placeholder,
            value,
            self.page.url,
            visible_options,
        )

    def _select_dropdown_by_placeholder(self, placeholder: str, value: str) -> None:
        clicked = self._open_dropdown_by_placeholder(placeholder)

        if not clicked:
            if value == "全部":
                logger.info("{} 使用重置后的无筛选状态表示“全部”", placeholder)
                return
            raise ValueError(f"未找到下拉选择器: {placeholder}")

        try:
            self._wait_for_visible_dropdown_options()
        except Exception:
            self._log_dropdown_options_not_found(placeholder, value)
            self.page.keyboard.press("Escape")
            if value == "全部":
                logger.info("{} 使用重置后的无筛选状态表示“全部”", placeholder)
                return
            raise ValueError(f"下拉选择器“{placeholder}”中未加载可见选项")

        if self._click_visible_dropdown_option(value):
            return

        fuzzy_option = self._find_unique_fuzzy_dropdown_option(value)
        if fuzzy_option and self._click_visible_dropdown_option(fuzzy_option):
            logger.info("模糊匹配下拉选项: {} -> {}", value, fuzzy_option)
            return

        self._log_dropdown_options_not_found(placeholder, value)
        self.page.keyboard.press("Escape")
        if value == "全部":
            logger.info("{} 使用重置后的无筛选状态表示“全部”", placeholder)
            return
        raise ValueError(f"下拉选择器“{placeholder}”中未找到选项: {value}")

    def _find_unique_fuzzy_dropdown_option(self, value: str) -> str | None:
        """Return the only sufficiently similar visible dropdown option."""
        normalized_value = self._normalize_dropdown_option(value)
        candidates = set(self._get_visible_dropdown_options())

        matches = [
            candidate
            for candidate in candidates
            if self._is_sufficient_fuzzy_match(normalized_value, self._normalize_dropdown_option(candidate))
        ]
        if len(matches) == 1:
            return matches[0]
        if matches:
            logger.warning("下拉选项模糊匹配不唯一: {} -> {}", value, matches)
        elif candidates:
            logger.warning("下拉选项无可用模糊匹配: {}，可见选项: {}", value, sorted(candidates))
        return None

    @staticmethod
    def _normalize_dropdown_option(value: str) -> str:
        return "".join(unicodedata.normalize("NFKC", value).split())

    @staticmethod
    def _is_sufficient_fuzzy_match(value: str, candidate: str) -> bool:
        if not value or not candidate:
            return False
        common_characters = len(set(value) & set(candidate))
        return common_characters >= 2 and common_characters / len(value) >= 0.5

    def _fill_input_by_placeholder(self, placeholder: str, value: str) -> None:
        selectors = [
            f'input[placeholder*="{placeholder}"]',
            f'.el-input__inner[placeholder*="{placeholder}"]',
            f'.ant-input[placeholder*="{placeholder}"]',
            f'//input[contains(@placeholder, "{placeholder}")]',
        ]
        for selector in selectors:
            try:
                locator = self.page.locator(selector)
                if locator.count() > 0:
                    locator.clear()
                    locator.fill(value)
                    logger.info(f"成功填充输入框: {selector}")
                    return
            except Exception:
                continue
        logger.warning(f"未找到输入框: {placeholder}")

    def _fill_range_input(self, label: str, begin: int, end: int) -> None:
        begin_selectors = [
            f'input[placeholder*="{label}"][placeholder*="开始"]',
            f'input[placeholder*="{label}"][placeholder*="起"]',
            f'.el-input__inner[placeholder*="{label}"][placeholder*="开始"]',
            f'.el-input__inner[placeholder*="{label}"][placeholder*="起"]',
            f'.ant-input[placeholder*="{label}"][placeholder*="开始"]',
            f'.ant-input[placeholder*="{label}"][placeholder*="起"]',
        ]
        end_selectors = [
            f'input[placeholder*="{label}"][placeholder*="结束"]',
            f'input[placeholder*="{label}"][placeholder*="止"]',
            f'.el-input__inner[placeholder*="{label}"][placeholder*="结束"]',
            f'.el-input__inner[placeholder*="{label}"][placeholder*="止"]',
            f'.ant-input[placeholder*="{label}"][placeholder*="结束"]',
            f'.ant-input[placeholder*="{label}"][placeholder*="止"]',
        ]

        for selector in begin_selectors:
            try:
                begin_locator = self.page.locator(selector)
                if begin_locator.count() > 0:
                    begin_locator.clear()
                    begin_locator.fill(str(begin))
                    break
            except Exception:
                continue

        for selector in end_selectors:
            try:
                end_locator = self.page.locator(selector)
                if end_locator.count() > 0:
                    end_locator.clear()
                    end_locator.fill(str(end))
                    break
            except Exception:
                continue

    def _fill_input(self, selector: str, value: str) -> None:
        selectors = [
            selector,
            f".el-input__inner{selector}",
            f".ant-input{selector}",
        ]
        for sel in selectors:
            try:
                locator = self.page.locator(sel)
                if locator.count() > 0:
                    locator.clear()
                    locator.fill(value)
                    return
            except Exception:
                continue
        logger.warning(f"未找到输入框: {selector}")

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

    @allure.step("获取响应时间")
    def measure_response_time(self) -> float:
        start = time.time()
        self.click_search()
        end = time.time()
        return end - start

    @allure.step("等待下拉选项加载")
    def wait_for_dropdown_options(self, timeout: int = 5000) -> None:
        option_selectors = [
            ".ant-select-dropdown-menu-item",
            ".ant-select-item-option-content",
            ".el-select-dropdown__item",
        ]
        for selector in option_selectors:
            try:
                self.page.wait_for_selector(selector, timeout=timeout // len(option_selectors))
                return
            except Exception:
                continue
        logger.warning("未找到下拉选项")

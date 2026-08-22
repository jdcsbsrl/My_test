import os
import re
import time

import allure
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class InventorySKUPage(BasePage):
    SEARCH_TIMEOUT_SECONDS = float(os.getenv("SKU_QUERY_TIMEOUT_SECONDS", "90"))

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.search_url = "product/productCenter/inventoryInfo"

    @allure.step("导航到库存SKU页面")
    def navigate_to_search_page(self) -> None:
        self.navigate_to(self.search_url)
        self.wait_for_load_state("domcontentloaded")
        ready_locator = self.page.locator("input, button, table, [role='table']").first
        try:
            ready_locator.wait_for(state="attached", timeout=30000)
        except PlaywrightTimeoutError:
            logger.warning(
                "库存SKU页面首屏控件未在30秒内出现，准备刷新重试: url={}, title={}",
                self.page.url,
                self.page.title(),
            )
            self.page.reload(wait_until="domcontentloaded", timeout=60000)
            ready_locator.wait_for(state="attached", timeout=45000)
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
            option = self.page.locator(f'.el-select-dropdown__item:has-text("{warehouse}")').first
            option.wait_for(state="visible", timeout=10000)
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

    @allure.step("选择导出勾选的库存SKU")
    def select_export_current_search(self) -> None:
        """Select current-search inventory SKU export and wait for export page."""
        self.click_export()
        menu = self.page.locator(".el-dropdown-menu__item:visible").first
        menu.wait_for(state="visible", timeout=10000)

        clicked = self.page.evaluate(
            """() => {
                const items = Array.from(document.querySelectorAll('.el-dropdown-menu__item'))
                    .filter(item => {
                        const rect = item.getBoundingClientRect();
                        const style = window.getComputedStyle(item);
                        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                    });
                for (const item of items) {
                    const text = item.textContent || "";
                    if (text.includes("\\u5f53\\u524d\\u641c\\u7d22") && text.toUpperCase().includes("SKU")) {
                        item.click();
                        return { clicked: true, text };
                    }
                }
                return { clicked: false, visibleTexts: items.map(item => item.textContent || "") };
            }"""
        )

        if not clicked.get("clicked"):
            raise ValueError(f"未找到可见的导出当前搜索库存SKU菜单项: {clicked}")

        logger.info("閫夋嫨瀵煎嚭褰撳墠鎼滅储鐨勫簱瀛楽KU: {}", clicked)
        try:
            self._wait_for_inventory_export_navigation()
        except TimeoutError:
            # The UAT Vue menu occasionally consumes the first synthetic click
            # while closing the dropdown. Reopen it and use a native locator
            # click once before treating navigation as a real failure.
            self.click_export()
            retry_item = self.page.locator(
                '.el-dropdown-menu__item:visible:has-text("导出当前搜索的库存SKU")'
            ).first
            retry_item.wait_for(state="visible", timeout=10000)
            retry_item.click(force=True)
            self._wait_for_inventory_export_navigation(timeout=30000)

    def _wait_for_inventory_export_navigation(self, timeout: int = 30000) -> None:
        start_time = time.time()
        while time.time() - start_time < timeout / 1000:
            if "exportPage" in self.page.url:
                return
            for opened_page in self.page.context.pages:
                if "exportPage" in opened_page.url:
                    self.page = opened_page
                    return
            self.wait_for_poll_interval(500)
        page_urls = [pg.url for pg in self.page.context.pages]
        raise TimeoutError(f"Inventory export page did not open. current={self.page.url}, pages={page_urls}")

    def select_export_selected(self) -> None:
        self.click_export()
        self.wait_for_page_settle(timeout=30000)
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
    def wait_for_search_results(self, timeout: int | None = None) -> None:
        timeout = int((timeout / 1000) if timeout is not None else self.SEARCH_TIMEOUT_SECONDS) * 1000
        try:
            self._wait_for_loading_finished(timeout)
            self.page.locator(
                ".virtual-pro-table:visible, table:visible, [role='table']:visible, .el-table:visible, .ant-table:visible, "
                ".el-table__empty-block:visible, .ant-empty:visible, [class*='empty']:visible"
            ).first.wait_for(state="visible", timeout=timeout)
        except Exception as exc:
            raise TimeoutError(f"库存SKU结果在 {timeout / 1000:.0f} 秒内未完成刷新") from exc

    def _click_inventory_checkbox(self, kind: str, row_index: int | None = None) -> bool:
        """Click the real checkbox rendered by Element Plus/Ant/VXE tables."""
        return bool(
            self.page.evaluate(
                """({ kind, rowIndex }) => {
                    const isVisible = (el) => {
                        if (!el) return false;
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    };
                    const clickableOf = (el) =>
                        el.closest('label.el-checkbox')
                        || el.closest('.el-checkbox')
                        || el.closest('.el-checkbox__input')
                        || el;
                    const selectors = kind === 'header'
                        ? [
                            '.el-table__header-wrapper .el-checkbox__inner',
                            '.el-table__header-wrapper .el-checkbox__original',
                            '.el-table__header-wrapper .el-checkbox',
                            'thead .el-checkbox__inner',
                            'thead .el-checkbox__original',
                            'thead .el-checkbox',
                            '.vxe-table--header-wrapper input[type="checkbox"]',
                            '.vxe-table--header-wrapper .el-checkbox__inner',
                            '.vxe-header--column .vxe-checkbox--icon',
                            '.ant-table-thead input[type="checkbox"]',
                            '.el-checkbox__inner',
                            '.el-checkbox__original',
                            '.el-checkbox'
                        ]
                        : [
                            '.el-table__body-wrapper .el-checkbox__original',
                            '.el-table__body-wrapper .el-checkbox__inner',
                            '.el-table__body-wrapper .el-checkbox',
                            'tbody .el-checkbox__original',
                            'tbody .el-checkbox__inner',
                            'tbody .el-checkbox',
                            '.vxe-table--body-wrapper input[type="checkbox"]',
                            '.vxe-table--body-wrapper .el-checkbox__inner',
                            '.ant-table-tbody input[type="checkbox"]',
                            '.el-checkbox__original',
                            '.el-checkbox__inner',
                            '.el-checkbox'
                        ];
                    const nodes = selectors.flatMap(selector => Array.from(document.querySelectorAll(selector)))
                        .filter(isVisible)
                        .sort((a, b) => {
                            const ar = a.getBoundingClientRect();
                            const br = b.getBoundingClientRect();
                            return (ar.y - br.y) || (ar.x - br.x);
                        });
                    const unique = [];
                    const seen = new Set();
                    for (const node of nodes) {
                        const clickable = clickableOf(node);
                        if (seen.has(clickable)) continue;
                        seen.add(clickable);
                        unique.push(node);
                    }
                    const target = kind === 'header' ? unique[0] : unique[rowIndex || 1];
                    if (!target) return false;
                    clickableOf(target).click();
                    return true;
                }""",
                {"kind": kind, "rowIndex": row_index},
            )
        )

    def _selected_row_count(self) -> int:
        return int(
            self.page.evaluate(
                """() => {
                    const clickableOf = (el) =>
                        el.closest('label.el-checkbox')
                        || el.closest('.el-checkbox')
                        || el.closest('.el-checkbox__input')
                        || el;
                    const visibleCheckboxes = Array.from(document.querySelectorAll(
                        '.el-checkbox__inner, .el-checkbox__original, .el-checkbox'
                    )).filter(el => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    }).sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.y - br.y) || (ar.x - br.x);
                    });
                    const headerCheckbox = visibleCheckboxes.length ? clickableOf(visibleCheckboxes[0]) : null;
                    const selectors = [
                        '.el-table__body-wrapper .el-checkbox__input.is-checked',
                        '.el-table__body-wrapper .el-checkbox.is-checked',
                        '.el-table__body-wrapper .el-checkbox__original:checked',
                        'tbody .el-checkbox__input.is-checked',
                        'tbody .el-checkbox.is-checked',
                        'tbody .el-checkbox__original:checked',
                        '.el-checkbox__original:checked',
                        '.el-checkbox__input.is-checked',
                        '.el-checkbox.is-checked',
                        '.ant-table-tbody input[type="checkbox"]:checked',
                        '.vxe-body--row.is--checked',
                        '.vxe-body--row.row--checked'
                    ];
                    const rows = new Set();
                    for (const selector of selectors) {
                        for (const node of document.querySelectorAll(selector)) {
                            if (headerCheckbox && clickableOf(node) === headerCheckbox) continue;
                            rows.add(node.closest('tr, .el-table__row, .vxe-body--row') || clickableOf(node));
                        }
                    }
                    return rows.size;
                }"""
            )
            or 0
        )

    def _header_checkbox_checked(self) -> bool:
        return bool(
            self.page.evaluate(
                """() => {
                    const clickableOf = (el) =>
                        el.closest('label.el-checkbox')
                        || el.closest('.el-checkbox')
                        || el.closest('.el-checkbox__input')
                        || el;
                    const nodes = Array.from(document.querySelectorAll([
                        '.el-table__header-wrapper .el-checkbox__inner',
                        '.el-table__header-wrapper .el-checkbox__original',
                        '.el-table__header-wrapper .el-checkbox',
                        'thead .el-checkbox__inner',
                        'thead .el-checkbox__original',
                        'thead .el-checkbox',
                        '.ant-table-thead input[type="checkbox"]',
                        '.vxe-table--header-wrapper input[type="checkbox"]',
                        '.el-checkbox__inner',
                        '.el-checkbox__original',
                        '.el-checkbox'
                    ].join(','))).filter(el => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    }).sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.y - br.y) || (ar.x - br.x);
                    });
                    const header = nodes.length ? clickableOf(nodes[0]) : null;
                    if (!header) return false;
                    const input = header.querySelector('input[type="checkbox"]');
                    return !!(input && input.checked)
                        || header.matches('input[type="checkbox"]:checked')
                        || header.classList.contains('is-checked')
                        || !!header.closest('.is-checked')
                        || header.getAttribute('aria-checked') === 'true';
                }"""
            )
        )

    @allure.step("Select all inventory SKU rows on current page")
    def select_all_current_page(self) -> None:
        """Select all rows on the current page through the real header checkbox."""
        if not self._click_inventory_checkbox("header"):
            raise ValueError("Header select-all checkbox was not found")
        try:
            self.page.wait_for_function(
                """() => {
                    const selectors = [
                        '.el-table__body-wrapper .el-checkbox__input.is-checked',
                        '.el-table__body-wrapper .el-checkbox.is-checked',
                        '.el-table__body-wrapper .el-checkbox__original:checked',
                        'tbody .el-checkbox__input.is-checked',
                        'tbody .el-checkbox.is-checked',
                        'tbody .el-checkbox__original:checked',
                        '.el-checkbox__original:checked',
                        '.el-checkbox__input.is-checked',
                        '.el-checkbox.is-checked',
                        '.ant-table-tbody input[type="checkbox"]:checked',
                        '.vxe-body--row.is--checked',
                        '.vxe-body--row.row--checked'
                    ];
                    return selectors.some(selector => document.querySelectorAll(selector).length > 0);
                }""",
                timeout=10000,
            )
        except Exception as exc:
            raise TimeoutError("No selected rows detected after clicking select-all") from exc
        logger.info("Selected all rows on current page")

    @allure.step("Deselect all inventory SKU rows")
    def deselect_all(self) -> None:
        if self.get_selected_count() == 0:
            return
        if not self._click_inventory_checkbox("header"):
            raise ValueError("Header select-all checkbox was not found")
        self.page.wait_for_function(
            """() => {
                const selectors = [
                    '.el-table__body-wrapper .el-checkbox__input.is-checked',
                    '.el-table__body-wrapper .el-checkbox.is-checked',
                    '.el-table__body-wrapper .el-checkbox__original:checked',
                    'tbody .el-checkbox__input.is-checked',
                    'tbody .el-checkbox.is-checked',
                    'tbody .el-checkbox__original:checked',
                    '.el-checkbox__original:checked',
                    '.el-checkbox__input.is-checked',
                    '.el-checkbox.is-checked',
                    '.ant-table-tbody input[type="checkbox"]:checked'
                ];
                return selectors.every(selector => document.querySelectorAll(selector).length === 0);
            }""",
            timeout=10000,
        )

    @allure.step("Select inventory SKU row: {row_index}")
    def select_row(self, row_index: int) -> None:
        """Select one row using the real row checkbox."""
        if not self._click_inventory_checkbox("row", row_index):
            raise ValueError(f"Row {row_index} checkbox was not found")
        try:
            self.page.wait_for_function(
                """expected => {
                    const selectors = [
                        '.el-table__body-wrapper .el-checkbox__input.is-checked',
                        '.el-table__body-wrapper .el-checkbox.is-checked',
                        '.el-table__body-wrapper .el-checkbox__original:checked',
                        'tbody .el-checkbox__input.is-checked',
                        'tbody .el-checkbox.is-checked',
                        'tbody .el-checkbox__original:checked',
                        '.el-checkbox__original:checked',
                        '.el-checkbox__input.is-checked',
                        '.el-checkbox.is-checked',
                        '.ant-table-tbody input[type="checkbox"]:checked'
                    ];
                    const rows = new Set();
                    for (const selector of selectors) {
                        for (const node of document.querySelectorAll(selector)) {
                            rows.add(node.closest('tr, .el-table__row') || node.closest('label.el-checkbox') || node.closest('.el-checkbox') || node);
                        }
                    }
                    return rows.size === expected;
                }""",
                arg=1,
                timeout=10000,
            )
        except Exception as exc:
            raise TimeoutError(f"Row {row_index} was not selected after click") from exc

    @allure.step("Get selected inventory SKU row count")
    def get_selected_count(self) -> int:
        try:
            return self._selected_row_count()
        except Exception:
            return 0

    @allure.step("Check inventory SKU header checkbox selected state")
    def is_header_checkbox_checked(self) -> bool:
        try:
            return self._header_checkbox_checked()
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

    @allure.step("Go to inventory SKU page {page_num}")
    def goto_page(self, page_num: int) -> None:
        total_pages = self.get_total_pages()
        if page_num < 1 or page_num > total_pages:
            raise ValueError(f"Target page {page_num} exceeds total pages {total_pages}")
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
                raise ValueError(f"Page {page_num} button or jump input was not found")
            page_input.fill(str(page_num))
            page_input.press("Enter")
        self.page.wait_for_function(
            """expected => {
                const active = document.querySelector(
                    '.el-pagination .el-pager li.is-active, '
                    + '.el-pagination .el-pager li.active, '
                    + '.ant-pagination-item-active'
                );
                return active && Number(active.textContent.trim()) === expected;
            }""",
            arg=page_num,
            timeout=10000,
        )
        self.wait_for_search_results()

    @allure.step("Click next inventory SKU page")
    def click_next_page(self) -> None:
        current_page = self.get_current_page()
        next_btn = self.page.locator(".el-pagination .btn-next, .ant-pagination-next").first
        if next_btn.count() == 0:
            raise ValueError("Next page button was not found")
        disabled = next_btn.evaluate(
            """node => node.disabled
                || node.getAttribute('aria-disabled') === 'true'
                || node.classList.contains('is-disabled')
                || node.classList.contains('disabled')"""
        )
        if disabled:
            raise ValueError("Next page button is disabled")
        next_btn.click(timeout=10000)
        self.page.wait_for_function(
            """previous => {
                const active = document.querySelector(
                    '.el-pagination .el-pager li.is-active, '
                    + '.el-pagination .el-pager li.active, '
                    + '.ant-pagination-item-active'
                );
                return active && Number(active.textContent.trim()) > previous;
            }""",
            arg=current_page,
            timeout=10000,
        )
        self.wait_for_search_results()

    @allure.step("Get current inventory SKU page number")
    def get_current_page(self) -> int:
        try:
            page = self.page.evaluate(
                """() => {
                const pagination = document.querySelector('.el-pagination');
                if (pagination && pagination.__vue__) {
                    const vm = pagination.__vue__;
                    if (vm.internalCurrentPage !== undefined) return vm.internalCurrentPage;
                }
                const active = document.querySelector(
                    '.el-pagination .el-pager li.is-active, '
                    + '.el-pagination .el-pager li.active, '
                    + '.el-pagination .is-active, '
                    + '.el-pagination .active, '
                    + '.ant-pagination-item-active'
                );
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

    @allure.step("Get total inventory SKU pages")
    def get_total_pages(self) -> int:
        try:
            pages = self.page.evaluate(
                """() => {
                const pagination = document.querySelector('.el-pagination');
                if (!pagination) return 1;
                const maxInput = pagination.querySelector('.el-pagination__jump input[max]');
                if (maxInput && maxInput.getAttribute('max')) {
                    const max = parseInt(maxInput.getAttribute('max'), 10);
                    if (!Number.isNaN(max) && max > 0) return max;
                }
                const last = Array.from(pagination.querySelectorAll('.el-pager li.number'))
                    .map(node => parseInt((node.textContent || '').trim(), 10))
                    .filter(num => !Number.isNaN(num))
                    .sort((a, b) => b - a)[0];
                if (last) return last;
                const total = pagination.querySelector('.el-pagination__total');
                const size = pagination.querySelector('.el-pagination__sizes input, .el-pagination__sizes .el-select__placeholder');
                const totalText = total ? total.textContent || '' : '';
                const sizeText = size ? size.value || size.textContent || '' : '';
                const totalCount = parseInt((totalText.match(/\\d+/) || ['0'])[0], 10);
                const pageSize = parseInt((sizeText.match(/\\d+/) || ['20'])[0], 10);
                return totalCount > 0 && pageSize > 0 ? Math.ceil(totalCount / pageSize) : 1;
            }"""
            )
            return int(pages) if pages else 1
        except Exception:
            return 1

    @allure.step("Get visible inventory SKU row count")
    def get_current_page_row_count(self) -> int:
        try:
            checkbox_rows = int(
                self.page.evaluate(
                    """() => {
                    const clickableOf = (el) =>
                        el.closest('label.el-checkbox')
                        || el.closest('.el-checkbox')
                        || el.closest('.el-checkbox__input')
                        || el;
                    const nodes = Array.from(document.querySelectorAll(
                        '.el-checkbox__inner, .el-checkbox__original, .el-checkbox'
                    )).filter(el => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    }).sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.y - br.y) || (ar.x - br.x);
                    });
                    const unique = [];
                    const seen = new Set();
                    for (const node of nodes) {
                        const clickable = clickableOf(node);
                        if (seen.has(clickable)) continue;
                        seen.add(clickable);
                        unique.push(clickable);
                    }
                    return Math.max(unique.length - 1, 0);
                }"""
                )
                or 0
            )
            if checkbox_rows > 0:
                return checkbox_rows
        except Exception:
            pass
        return int(
            self.page.locator(
                ".el-table__body-wrapper tr:visible, .el-table__row:visible, "
                ".ant-table-tbody tr:visible, .vxe-body--row:visible"
            ).count()
        )

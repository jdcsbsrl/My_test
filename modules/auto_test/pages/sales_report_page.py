import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import allure
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class SalesReportPage(BasePage):
    """Sales product sales report page."""

    report_url = "sales/salesReport/salesReport"

    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.last_search_payload: dict[str, Any] | None = None
        self.last_sort_payloads: list[dict[str, Any] | None] = []

    def _api_prefix(self) -> str:
        """Use the API path belonging to the active test environment."""
        return urlsplit(self.config.api_base_url).path.rstrip("/")

    @allure.step("Navigate to sales product sales report")
    def navigate_to_report(self) -> None:
        self.navigate_to(self.report_url)
        self.page.wait_for_load_state("domcontentloaded")
        self.wait_for_table_ready()

    def wait_for_table_ready(self, timeout: int = 45000) -> None:
        self._wait_for_loading_finished(timeout)
        self.page.locator(".el-table:visible, table:visible").first.wait_for(state="visible", timeout=timeout)
        try:
            self.page.wait_for_function(
                """() => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden';
                    };
                    const rows = Array.from(document.querySelectorAll(
                        '.el-table__body-wrapper tbody tr, tbody tr'
                    )).filter(visible);
                    const empty = Array.from(document.querySelectorAll(
                        '.el-table__empty-block, .el-table__empty-text, [class*="empty"]'
                    )).some((el) => visible(el) && (el.innerText || el.textContent || '').trim());
                    return rows.length > 0 || empty;
                }""",
                timeout=timeout,
            )
        except Exception:
            logger.warning("Sales report table container is visible but rows did not stabilize within timeout")

    def _wait_for_loading_finished(self, timeout: int = 30000) -> None:
        try:
            self.page.locator(".el-loading-mask:visible, .ant-spin-spinning:visible").first.wait_for(
                state="hidden", timeout=timeout
            )
        except Exception:
            pass

    @allure.step("Click sales report search")
    def search(self) -> None:
        captured_payload: dict[str, Any] | None = None

        def on_request(request: Any) -> None:
            nonlocal captured_payload
            if "salesproductreport/productsalesreport" not in request.url.lower():
                return
            try:
                post_data_json = request.post_data_json
                captured_payload = post_data_json() if callable(post_data_json) else post_data_json
            except Exception:
                captured_payload = {"raw": request.post_data or ""}

        self.page.on("request", on_request)
        self._click_visible_button("搜索")
        self.wait_for_table_ready()
        self.wait_for_loading_complete(timeout=30000)
        self.page.remove_listener("request", on_request)
        self.last_search_payload = captured_payload

    @allure.step("Click sales report reset")
    def reset(self) -> None:
        self._click_visible_button("重置")
        self.wait_for_table_ready()

    def _click_visible_button(self, text: str) -> None:
        clicked = self.page.evaluate(
            """(text) => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const buttons = Array.from(document.querySelectorAll('button'))
                    .filter(isVisible);
                const button = buttons.find((el) => (el.innerText || el.textContent || '').includes(text));
                if (!button) return false;
                button.click();
                return true;
            }""",
            text,
        )
        if not clicked:
            raise ValueError(f"Button not found: {text}")

    def fill_input(self, placeholder_keyword: str, value: str) -> None:
        locator = self.page.locator(f'input[placeholder*="{placeholder_keyword}"]').first
        locator.wait_for(state="visible", timeout=10000)
        locator.fill(value)

    def fill_sku_code(self, value: str) -> None:
        self.fill_input("SKU编码", value)

    def fill_sku_cn(self, value: str) -> None:
        self.fill_input("SKU中文", value)

    def fill_sku_en(self, value: str) -> None:
        self.fill_input("SKU英文", value)

    def fill_variant_id(self, value: str) -> None:
        self.fill_input("变体ID", value)

    def fill_sku_create_date(self, start_date: str, end_date: str | None = None) -> None:
        end_date = end_date or start_date
        start_value = start_date if len(start_date) > 10 else f"{start_date} 00:00:00"
        end_value = end_date if len(end_date) > 10 else f"{end_date} 23:59:59"
        filled = self.page.evaluate(
            """([startValue, endValue]) => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const items = Array.from(document.querySelectorAll('.el-form-item')).filter(visible);
                const item = items.find((el) => {
                    const label = el.querySelector('.el-form-item__label');
                    return label && (label.innerText || label.textContent || '').includes('SKU创建日期');
                });
                if (!item) return false;
                const inputs = Array.from(item.querySelectorAll('input'));
                if (inputs.length < 2) return false;
                const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                [startValue, endValue].forEach((value, index) => {
                    const input = inputs[index];
                    input.removeAttribute('readonly');
                    setter.call(input, value);
                    input.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: value }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    input.dispatchEvent(new KeyboardEvent('keydown', { bubbles: true, key: 'Enter', code: 'Enter' }));
                    input.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: 'Enter', code: 'Enter' }));
                    input.blur();
                });
                return true;
            }""",
            [start_value, end_value],
        )
        if not filled:
            raise ValueError("SKU create date range inputs were not found")
        self.page.keyboard.press("Escape")

    def sku_create_date_values(self) -> list[str]:
        return self.page.evaluate(
            """() => {
                const items = Array.from(document.querySelectorAll('.el-form-item'));
                const item = items.find((el) => {
                    const label = el.querySelector('.el-form-item__label');
                    return label && (label.innerText || label.textContent || '').includes('SKU创建日期');
                });
                if (!item) return [];
                return Array.from(item.querySelectorAll('input')).map((input) => input.value);
            }"""
        )

    def select_dropdown_by_label(self, label_text: str, option_text: str) -> bool:
        try:
            form_item = self.page.locator(".el-form-item").filter(has_text=label_text).first
            form_item.locator(".el-select__wrapper, .el-cascader, .store-select-trigger").first.click(
                force=True, timeout=10000
            )
            option = self.page.locator("li.el-select-dropdown__item, .el-cascader-node").filter(
                has_text=option_text
            ).first
            option.wait_for(state="visible", timeout=10000)
            option.click(force=True, timeout=10000)
            self.page.keyboard.press("Escape")
            return True
        except Exception:
            self.page.keyboard.press("Escape")

        result = self.page.evaluate(
            """({ labelText, optionText }) => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const formItems = Array.from(document.querySelectorAll('.el-form-item'));
                const item = formItems.find((el) => (el.innerText || '').includes(labelText));
                const select = item && item.querySelector(
                    '.el-select__wrapper, .el-cascader, .store-select-trigger, .el-select, input'
                );
                if (!select) return { opened: false };
                select.click();
                return { opened: true };
            }""",
            {"labelText": label_text, "optionText": option_text},
        )
        if not result.get("opened"):
            return False
        clicked = self.page.evaluate(
            """(optionText) => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const candidates = Array.from(document.querySelectorAll(
                    'li.el-select-dropdown__item, .el-cascader-node, [role="option"]'
                )).filter(isVisible);
                const option = candidates.find((el) => (el.innerText || el.textContent || '').includes(optionText));
                if (!option) return false;
                option.click();
                return true;
            }""",
            option_text,
        )
        self.page.keyboard.press("Escape")
        return bool(clicked)

    def row_count(self) -> int:
        return int(
            self.page.evaluate(
                """() => Array.from(document.querySelectorAll('.el-table__body-wrapper tbody tr, tbody tr'))
                    .filter((row) => {
                        const rect = row.getBoundingClientRect();
                        const style = window.getComputedStyle(row);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && !row.className.includes('expanded');
                    })
                    .filter((row) => row.querySelectorAll('td').length >= 5)
                    .length"""
            )
            or 0
        )

    def total_count(self) -> int:
        body_text = self.page.locator("body").inner_text(timeout=5000)
        match = re.search(r"共\s*(\d+)\s*条", body_text)
        if match:
            return int(match.group(1))
        return self.row_count()

    def first_row(self) -> dict[str, str]:
        rows = self.visible_rows(limit=1)
        if not rows:
            raise AssertionError("Sales report table has no visible rows")
        return rows[0]

    def visible_rows(self, limit: int = 20) -> list[dict[str, str]]:
        return self.page.evaluate(
            """(limit) => {
                const text = (el) => (el && (el.innerText || el.textContent) || '').trim();
                const headerNodes = Array.from(document.querySelectorAll(
                    '.vxe-header--row th, .el-table__header-wrapper th, thead th'
                ));
                const headers = headerNodes.map((el) => text(el).replace(/\\s+/g, ' '));
                const uniqueHeaders = [];
                for (const header of headers) {
                    uniqueHeaders.push(header);
                }
                const rows = Array.from(document.querySelectorAll(
                    '.vxe-body--row, .el-table__body-wrapper tbody tr, tbody tr'
                ))
                    .filter((row) => {
                        const rect = row.getBoundingClientRect();
                        const style = window.getComputedStyle(row);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && !row.className.includes('expanded');
                    })
                    .filter((row) => row.querySelectorAll('td').length >= 5)
                    .slice(0, limit);
                return rows.map((row) => {
                    let cells = Array.from(row.querySelectorAll('td')).map((cell) => text(cell));
                    if (cells.length > uniqueHeaders.length) {
                        cells = cells.slice(cells.length - uniqueHeaders.length);
                    }
                    const result = {};
                    for (let i = 0; i < Math.min(uniqueHeaders.length, cells.length); i += 1) {
                        if (uniqueHeaders[i]) {
                            result[uniqueHeaders[i]] = cells[i];
                        }
                    }
                    return result;
                });
            }""",
            limit,
        )

    def assert_column_contains(self, column_name: str, expected: str) -> None:
        rows = self.visible_rows()
        assert rows, "Search returned no visible rows"
        normalized_expected = expected.strip().lower()
        matched = any(normalized_expected in row.get(column_name, "").lower() for row in rows)
        assert matched, f"Column {column_name} does not contain {expected}; rows={rows[:3]}"

    def current_page(self) -> int:
        value = self.page.locator(".el-pagination__jump input").first.input_value(timeout=5000)
        return int(value or 1)

    def click_page_number(self, page_number: int) -> bool:
        clicked = self.page.evaluate(
            """(pageNumber) => {
                const items = Array.from(document.querySelectorAll('.el-pager li'));
                const item = items.find((el) => (el.innerText || el.textContent || '').trim() === String(pageNumber));
                if (!item || item.classList.contains('is-active')) return false;
                item.click();
                return true;
            }""",
            page_number,
        )
        if clicked:
            self.wait_for_table_ready()
        return bool(clicked)

    def next_page(self) -> bool:
        next_button = self.page.locator(".el-pagination .btn-next").first
        if next_button.count() == 0 or next_button.is_disabled():
            return False
        next_button.click()
        self.wait_for_table_ready()
        return True

    def click_sort(self, column_name: str, direction: str = "desc") -> list[float]:
        captured_payload: dict[str, Any] | None = None

        def on_request(request: Any) -> None:
            nonlocal captured_payload
            if "salesproductreport/productsalesreport" not in request.url.lower():
                return
            try:
                post_data_json = request.post_data_json
                captured_payload = post_data_json() if callable(post_data_json) else post_data_json
            except Exception:
                captured_payload = {"raw": request.post_data or ""}

        self.page.on("request", on_request)
        clicked = self.page.evaluate(
            """([columnName, direction]) => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const headers = Array.from(document.querySelectorAll('th, .vxe-header--column'))
                    .filter(visible);
                const header = headers.find((el) => (el.innerText || el.textContent || '').includes(columnName));
                if (!header) return false;
                const preferredSelectors = direction === 'asc'
                    ? ['.vxe-sort--asc-btn', '.ascending', '.sort-caret.ascending']
                    : ['.vxe-sort--desc-btn', '.descending', '.sort-caret.descending'];
                let sortHandle = null;
                for (const selector of preferredSelectors) {
                    sortHandle = header.querySelector(selector);
                    if (sortHandle) break;
                }
                sortHandle = sortHandle || header.querySelector('.caret-wrapper, .vxe-cell--sort');
                (sortHandle || header).click();
                return true;
            }""",
            [column_name, direction],
        )
        if not clicked:
            self.page.remove_listener("request", on_request)
            raise ValueError(f"Sortable header not found: {column_name}")
        self.wait_for_table_ready()
        self.wait_for_table_ready()
        self.page.remove_listener("request", on_request)
        self.last_sort_payloads.append(captured_payload)
        return self.numeric_column_values(column_name)

    def numeric_column_values(self, column_name: str, limit: int = 20) -> list[float]:
        mapped_values = self._parse_numeric_values(
            row.get(column_name, "") for row in self.visible_rows(limit=limit)
        )
        if mapped_values:
            return mapped_values

        raw_values = self.page.evaluate(
            """([columnName, limit]) => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const headers = Array.from(document.querySelectorAll('th, .vxe-header--column'))
                    .filter(visible)
                    .map((el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' '));
                const uniqueHeaders = headers.filter((header, index) => header && headers.indexOf(header) === index);
                const columnIndex = uniqueHeaders.findIndex((header) => header.includes(columnName));
                if (columnIndex < 0) return [];
                const rows = Array.from(document.querySelectorAll(
                    '.vxe-body--row, .el-table__body-wrapper tbody tr'
                )).filter((row) => visible(row) && !row.className.includes('expanded')).slice(0, limit);
                return rows.map((row) => {
                    let cells = Array.from(row.querySelectorAll('td, .vxe-body--column'))
                        .filter(visible)
                        .map((cell) => (cell.innerText || cell.textContent || '').trim().replace(/\\s+/g, ' '));
                    if (cells.length > uniqueHeaders.length) {
                        cells = cells.slice(cells.length - uniqueHeaders.length);
                    }
                    return cells[columnIndex] || '';
                });
            }""",
            [column_name, limit],
        )
        return self._parse_numeric_values(raw_values)

    @staticmethod
    def _parse_numeric_values(raw_values: Any) -> list[float]:
        values = []
        for raw_value in raw_values:
            raw = raw_value.strip().replace(",", "")
            if not raw or raw == "-":
                continue
            match = re.search(r"-?\d+(?:\.\d+)?", raw)
            if match:
                values.append(float(match.group(0)))
        return values

    @staticmethod
    def is_sorted(values: list[float], direction: str | None = None) -> bool:
        if len(values) < 2:
            return True
        ascending = all(left <= right for left, right in zip(values, values[1:]))
        descending = all(left >= right for left, right in zip(values, values[1:]))
        if direction == "asc":
            return ascending
        if direction == "desc":
            return descending
        return ascending or descending

    def sort_and_assert_numeric_order(self, column_name: str) -> dict[str, Any]:
        self.last_sort_payloads = []
        desc_values = self.click_sort(column_name, "desc")
        desc_sorted = self.is_sorted(desc_values, "desc")
        asc_values = self.click_sort(column_name, "asc")
        asc_sorted = self.is_sorted(asc_values, "asc")
        return {
            "column": column_name,
            "desc_values": desc_values,
            "asc_values": asc_values,
            "payloads": self.last_sort_payloads,
            "passed": bool(desc_values) and bool(asc_values) and desc_sorted and asc_sorted,
        }

    def expand_first_row(self) -> int:
        before = self.expanded_row_count()
        before_body = self.page.locator(".vxe-table--body-wrapper, .el-table__body-wrapper").first.inner_text(
            timeout=5000
        )
        # The sales report uses VXETable's stable expand control.
        expand_button = self.page.locator(".vxe-table--expand-btn:visible").first
        if expand_button.count() > 0:
            expand_button.click(force=True, timeout=10000)
            self.wait_for_poll_interval(500)
            self.page.wait_for_function(
                """() => document.querySelectorAll(
                    '.el-table__expanded-cell, tr.el-table__expanded-row, '
                    + '.vxe-body--expanded-row, .vxe-expanded-cell, '
                    + '.vxe-table--expanded-row, .p-6px .vxe-table'
                ).length > 0""",
                timeout=15000,
            )
            after = self.expanded_row_count()
            after_body = self.page.locator(
                ".vxe-table--body-wrapper, .el-table__body-wrapper"
            ).first.inner_text(timeout=5000)
            expanded_class_count = self.page.locator(
                ".row--expanded:visible, .is--expanded:visible, .p-6px .vxe-table:visible"
            ).count()
            assert after > before or expanded_class_count > 0 or after_body != before_body, (
                f"Expanded row did not appear: before={before}, after={after}, "
                f"expanded_class_count={expanded_class_count}"
            )
            return after
        clicked = self.page.evaluate(
            """() => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const candidates = Array.from(document.querySelectorAll(
                    '.vxe-table--expanded, .vxe-cell--wrapper:has(.vxe-table--expand-btn), '
                    + '.vxe-table--expand-btn.vxe-table-icon-arrow-right, '
                    + '.el-table__expand-icon, .el-table__expand-icon .el-icon, .el-table__expand-column, '
                    + '.vxe-icon-caret-right, .vxe-cell--expand-icon, .vxe-body--row td.col--expand, '
                    + '.vxe-body--row .col--expand'
                )).filter((el) => visible(el) && !el.className.includes('fixed--hidden'));
                const target = candidates[0];
                if (!target) return false;
                const rect = target.getBoundingClientRect();
                const eventOptions = {
                    bubbles: true,
                    cancelable: true,
                    clientX: rect.left + Math.min(24, Math.max(4, rect.width / 2)),
                    clientY: rect.top + rect.height / 2,
                    view: window,
                };
                const clickTarget = target.querySelector('.vxe-table--expand-btn') || target;
                clickTarget.click();
                return true;
            }"""
        )
        if not clicked:
            raise ValueError("No expandable row control was found")
        # The detail request is asynchronous; yield to the browser event loop
        # before checking the expanded-row DOM state.
        self.wait_for_poll_interval(500)
        self.page.wait_for_function(
            """() => document.querySelectorAll(
                '.el-table__expanded-cell, tr.el-table__expanded-row, '
                + '.vxe-body--expanded-row, .vxe-expanded-cell, '
                + '.vxe-table--expanded-row, .p-6px .vxe-table'
            ).length > 0""",
            timeout=15000,
        )
        after = self.expanded_row_count()
        after_body = self.page.locator(".vxe-table--body-wrapper, .el-table__body-wrapper").first.inner_text(
            timeout=5000
        )
        expanded_class_count = self.page.locator(
            ".row--expanded:visible, .is--expanded:visible, .p-6px .vxe-table:visible"
        ).count()
        assert after > before or expanded_class_count > 0 or after_body != before_body, (
            f"Expanded row did not appear: before={before}, after={after}, "
            f"expanded_class_count={expanded_class_count}"
        )
        return after

    def expanded_detail_rows(self, limit: int = 20) -> list[dict[str, str]]:
        return self.page.evaluate(
            """(limit) => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const table = Array.from(document.querySelectorAll('.p-6px .vxe-table')).find(visible);
                if (!table) return [];
                const headers = Array.from(table.querySelectorAll('.vxe-header--column, th'))
                    .filter(visible)
                    .map((el) => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' '));
                const uniqueHeaders = headers.filter((header, index) => header && headers.indexOf(header) === index);
                const rows = Array.from(table.querySelectorAll('.vxe-body--row, tbody tr'))
                    .filter((row) => visible(row))
                    .slice(0, limit);
                return rows.map((row) => {
                    const cells = Array.from(row.querySelectorAll('.vxe-body--column, td'))
                        .filter(visible)
                        .map((cell) => (cell.innerText || cell.textContent || '').trim().replace(/\\s+/g, ' '));
                    const result = {};
                    for (let i = 0; i < Math.min(uniqueHeaders.length, cells.length); i += 1) {
                        if (uniqueHeaders[i]) result[uniqueHeaders[i]] = cells[i];
                    }
                    return result;
                });
            }""",
            limit,
        )

    def has_expand_control(self) -> bool:
        return bool(
            self.page.evaluate(
                """() => Array.from(document.querySelectorAll(
                    '.vxe-table--expanded, .vxe-cell--wrapper:has(.vxe-table--expand-btn), '
                    + '.vxe-table--expand-btn.vxe-table-icon-arrow-right, '
                    + '.el-table__expand-icon, .vxe-icon-caret-right, .vxe-cell--expand-icon, '
                    + '.vxe-cell--tree-node .vxe-tree--btn-wrapper, .vxe-body--row td.col--expand, '
                    + '.vxe-body--row .col--expand'
                )).some((el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && !el.className.includes('fixed--hidden')
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                })"""
            )
        )

    def expanded_row_count(self) -> int:
        return self.page.locator(
            ".el-table__expanded-cell:visible, tr.el-table__expanded-row:visible, "
            + ".vxe-body--expanded-row:visible, .vxe-expanded-cell:visible, "
            + ".vxe-table--expanded-row:visible, .p-6px .vxe-table:visible"
        ).count()

    def export_menu_options(self) -> list[str]:
        return self.page.evaluate(
            """() => Array.from(document.querySelectorAll('button'))
                .filter((el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== 'none' && style.visibility !== 'hidden';
                })
                .map((el) => (el.innerText || el.textContent || '').trim())
                .filter((text) => text.includes('导出'))"""
        )

    def export_by_menu_text(self, menu_text: str, download_dir: str, timeout: int = 60000) -> dict[str, Any]:
        Path(download_dir).mkdir(parents=True, exist_ok=True)
        downloads = []
        responses = []

        def on_download(download: Any) -> None:
            downloads.append(download)

        def on_response(response: Any) -> None:
            url = response.url.lower()
            if "export" in url or "salesproductreport" in url or "salesreport" in url:
                responses.append({"url": response.url, "status": response.status})

        self.page.on("download", on_download)
        self.page.on("response", on_response)
        try:
            clicked = self.page.evaluate(
                """() => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== 'none' && style.visibility !== 'hidden';
                    };
                    const button = Array.from(document.querySelectorAll('button'))
                        .filter(visible)
                        .find((el) => (el.innerText || el.textContent || '').includes('导出'));
                    if (!button) return false;
                    button.click();
                    return true;
                }"""
            )
            if not clicked:
                raise ValueError("Export button not found")
            deadline = time.time() + timeout / 1000
            while time.time() < deadline:
                if downloads:
                    download = downloads[0]
                    target = Path(download_dir) / download.suggested_filename
                    download.save_as(str(target))
                    return {
                        "success": target.exists() and target.stat().st_size > 0,
                        "mode": "download",
                        "file_path": str(target),
                        "file_size": target.stat().st_size if target.exists() else 0,
                        "filename": download.suggested_filename,
                    }
                self.wait_for_poll_interval(1000)
            if any(item["status"] < 400 for item in responses):
                return {"success": True, "mode": "async_response", "responses": responses}
            return {"success": False, "mode": "timeout", "responses": responses}
        finally:
            self.page.remove_listener("download", on_download)
            self.page.remove_listener("response", on_response)

    def trigger_async_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.page.evaluate(
            """async ({ payload, apiPrefix }) => {
                const authHeaders = (() => {
                    const read = (key) => localStorage.getItem(key) || sessionStorage.getItem(key) || '';
                    const tokenKeys = ['Admin-Token', 'access_token', 'accessToken', 'token', 'Authorization'];
                    let token = '';
                    for (const key of tokenKeys) {
                        token = read(key);
                        if (token) break;
                    }
                    const clientid = read('clientid') || read('client_id') || read('Clientid') || read('CLIENT_ID');
                    const headers = {};
                    if (token) {
                        const bearer = token.startsWith('Bearer ') ? token : `Bearer ${token}`;
                        headers.Authorization = bearer;
                        headers['Admin-Token'] = token.replace(/^Bearer\\s+/i, '');
                    }
                    if (clientid) headers.clientid = clientid;
                    return headers;
                })();
                const response = await fetch(
                    `${apiPrefix}/oms-admin/sales/salesProductReport/syncProductSalesReportExport`,
                    {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'content-type': 'application/json;charset=UTF-8', ...authHeaders },
                        body: JSON.stringify(payload),
                    },
                );
                const contentType = response.headers.get('content-type') || '';
                let body;
                if (contentType.toLowerCase().includes('json')) {
                    body = await response.json();
                } else {
                    body = await response.text();
                }
                return {
                    ok: response.ok,
                    status: response.status,
                    url: response.url,
                    body,
                    headers: Object.fromEntries(response.headers.entries()),
                };
            }""",
            {"payload": payload, "apiPrefix": self._api_prefix()},
        )
        return {
            "ok": result["ok"],
            "status": result["status"],
            "url": result["url"],
            "payload": payload,
            "body": result["body"],
            "headers": result["headers"],
        }

    def query_report_api(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.page.evaluate(
            """async ({ payload, apiPrefix }) => {
                const authHeaders = (() => {
                    const read = (key) => localStorage.getItem(key) || sessionStorage.getItem(key) || '';
                    const tokenKeys = ['Admin-Token', 'access_token', 'accessToken', 'token', 'Authorization'];
                    let token = '';
                    for (const key of tokenKeys) {
                        token = read(key);
                        if (token) break;
                    }
                    const clientid = read('clientid') || read('client_id') || read('Clientid') || read('CLIENT_ID');
                    const headers = {};
                    if (token) {
                        const bearer = token.startsWith('Bearer ') ? token : `Bearer ${token}`;
                        headers.Authorization = bearer;
                        headers['Admin-Token'] = token.replace(/^Bearer\\s+/i, '');
                    }
                    if (clientid) headers.clientid = clientid;
                    return headers;
                })();
                const response = await fetch(
                    `${apiPrefix}/oms-admin/sales/salesProductReport/productSalesReport`,
                    {
                        method: 'POST',
                        credentials: 'include',
                        headers: { 'content-type': 'application/json;charset=UTF-8', ...authHeaders },
                        body: JSON.stringify(payload),
                    },
                );
                const contentType = response.headers.get('content-type') || '';
                const body = contentType.toLowerCase().includes('json')
                    ? await response.json()
                    : await response.text();
                return {
                    ok: response.ok,
                    status: response.status,
                    url: response.url,
                    body,
                };
            }""",
            {"payload": payload, "apiPrefix": self._api_prefix()},
        )

    def snapshot(self, name: str) -> str:
        path = Path(".runtime/reports/screenshots") / f"{name}_{int(time.time())}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)
        return str(path)

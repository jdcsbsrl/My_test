"""Simple test for sales order export - debug version."""

import os
import sys
import time

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import SalesOrderExportPage
from modules.auto_test.pages.sales_order_page import SalesOrderPage


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestSalesExportSimple:
    """Simple test for export flow."""

    def test_simple_export(self, logged_in_page: Page) -> None:
        """Simple export test."""
        sys.stdout.write("\n=== Starting simple export test ===\n")
        sys.stdout.flush()

        sales_order_page = SalesOrderPage(logged_in_page)
        export_page = SalesOrderExportPage(logged_in_page)

        sys.stdout.write("\nStep 1: Check home page after login\n")
        sys.stdout.flush()
        logged_in_page.wait_for_timeout(5000)

        page_info = logged_in_page.evaluate(
            """
            () => {
                const info = {};
                info.title = document.title;
                info.url = window.location.href;
                info.bodyClass = document.body.className;
                info.allButtons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t);
                info.divClasses = Array.from(document.querySelectorAll('div')).map(d => d.className).filter(c => c && c.length > 0 && c.length < 80).slice(0, 50);
                info.allText = Array.from(document.querySelectorAll('span, div')).map(e => e.innerText.trim()).filter(t => t && t.length < 30).slice(0, 100);
                return info;
            }
        """
        )
        sys.stdout.write(f"Page title: {page_info.get('title', 'N/A')}\n")
        sys.stdout.write(f"URL: {page_info.get('url', 'N/A')}\n")
        sys.stdout.write(f"Body class: {page_info.get('bodyClass', 'N/A')}\n")
        sys.stdout.write(f"Buttons found: {page_info.get('allButtons', [])}\n")
        sys.stdout.write(f"Div classes (sample): {page_info.get('divClasses', [])}\n")
        sys.stdout.write(f"All text (sample): {page_info.get('allText', [])}\n")
        sys.stdout.flush()

        sys.stdout.write("\nStep 2: Check sidebar status and expand if needed\n")
        sys.stdout.flush()
        sidebar_info = logged_in_page.evaluate(
            """
            () => {
                const sidebar = document.querySelector('.sidebar-container');
                const isCollapsed = sidebar && sidebar.classList.contains('collapse');
                console.log('Sidebar collapsed:', isCollapsed);
                
                const expandBtn = document.querySelector('.sidebar-logo-container');
                if (expandBtn && isCollapsed) {
                    expandBtn.click();
                    console.log('Clicked expand button');
                    return 'expanded';
                }
                return isCollapsed ? 'collapsed' : 'already-expanded';
            }
        """
        )
        sys.stdout.write(f"Sidebar status: {sidebar_info}\n")
        sys.stdout.flush()
        logged_in_page.wait_for_timeout(3000)

        sys.stdout.write("\nStep 2.1: Navigate via menu - click '销售'\n")
        sys.stdout.flush()
        menu_nav_result = logged_in_page.evaluate(
            """
            () => {
                const allElements = Array.from(document.querySelectorAll('.sq-menu-item'));
                console.log('Total sq-menu-item:', allElements.length);
                
                for (const item of allElements) {
                    const text = item.innerText.trim();
                    if (text.includes('销售')) {
                        item.click();
                        console.log('Clicked item: ' + text);
                        return text;
                    }
                }
                
                const spans = Array.from(document.querySelectorAll('span'));
                for (const span of spans) {
                    const text = span.innerText.trim();
                    if (text === '销售' || text === '销售订单') {
                        span.click();
                        console.log('Clicked span: ' + text);
                        return text;
                    }
                }
                return null;
            }
        """
        )
        sys.stdout.write(f"Menu navigation result: {menu_nav_result}\n")
        sys.stdout.flush()
        logged_in_page.wait_for_timeout(8000)

        sys.stdout.write("\nStep 2.1: Click '销售订单导出' in drawer\n")
        sys.stdout.flush()
        drawer_items = logged_in_page.evaluate(
            """
            () => {
                const items = Array.from(document.querySelectorAll('.sq-drawer-item'));
                const itemTexts = items.map(item => item.innerText.trim());
                console.log('Drawer items:', itemTexts);
                for (const item of items) {
                    const text = item.innerText.trim();
                    if (text.includes('销售订单导出') || text.includes('订单导出')) {
                        item.click();
                        console.log('Clicked drawer item: ' + text);
                        return text;
                    }
                }
                return null;
            }
        """
        )
        sys.stdout.write(f"Drawer item clicked: {drawer_items}\n")
        sys.stdout.flush()
        logged_in_page.wait_for_timeout(15000)

        sys.stdout.write(f"Current URL: {logged_in_page.url}\n")
        sys.stdout.flush()

        page_info = logged_in_page.evaluate(
            """
            () => {
                const info = {};
                info.title = document.title;
                info.allButtons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t);
                info.divClasses = Array.from(document.querySelectorAll('div')).map(d => d.className).filter(c => c && c.length > 0 && c.length < 80).slice(0, 50);
                return info;
            }
        """
        )
        sys.stdout.write(f"Page title: {page_info.get('title', 'N/A')}\n")
        sys.stdout.write(f"Buttons found: {page_info.get('allButtons', [])}\n")
        sys.stdout.flush()

        sys.stdout.write("\nStep 3: Find and click export button\n")
        sys.stdout.flush()
        export_result = logged_in_page.evaluate(
            """
            () => {
                const allElements = Array.from(document.querySelectorAll('.sq-drawer-item'));
                for (const item of allElements) {
                    const text = item.innerText.trim();
                    if (text.includes('销售订单导出')) {
                        item.click();
                        console.log('Clicked drawer item: ' + text);
                        return text;
                    }
                }
                const buttons = Array.from(document.querySelectorAll('button'));
                for (const btn of buttons) {
                    const text = btn.innerText.trim();
                    if (text.includes('导出')) {
                        btn.click();
                        console.log('Clicked export button: ' + text);
                        return text;
                    }
                }
                const spans = Array.from(document.querySelectorAll('span'));
                for (const span of spans) {
                    const text = span.innerText.trim();
                    if (text.includes('导出')) {
                        span.click();
                        console.log('Clicked export span: ' + text);
                        return text;
                    }
                }
                return null;
            }
        """
        )
        sys.stdout.write(f"Export button clicked: {export_result}\n")
        sys.stdout.flush()
        logged_in_page.wait_for_timeout(10000)

        sys.stdout.write("\nStep 3.1: Check all tabs/pages\n")
        sys.stdout.flush()
        pages_info = logged_in_page.context.pages
        for i, pg in enumerate(pages_info):
            sys.stdout.write(f"Page {i}: URL={pg.url}, Title={pg.title()}\n")
            sys.stdout.flush()
        if len(pages_info) > 1:
            logged_in_page = logged_in_page.context.pages[-1]
            sys.stdout.write(f"Switched to page: {logged_in_page.url}\n")
            sys.stdout.flush()
            logged_in_page.wait_for_timeout(5000)

        sys.stdout.write("\nStep 4: Select export option\n")
        sys.stdout.flush()
        select_result = logged_in_page.evaluate(
            """
            () => {
                const allElements = Array.from(document.querySelectorAll('div, span, li'));
                for (const el of allElements) {
                    const text = el.innerText.trim();
                    if (text.includes('导出当前') || text.includes('当前搜索')) {
                        el.click();
                        console.log('Selected export option: ' + text);
                        return text;
                    }
                }
                return null;
            }
        """
        )
        sys.stdout.write(f"Export option selected: {select_result}\n")
        sys.stdout.flush()
        logged_in_page.wait_for_timeout(15000)

        sys.stdout.write(f"Current URL: {logged_in_page.url}\n")
        sys.stdout.flush()

        page_info = logged_in_page.evaluate(
            """
            () => {
                const info = {};
                info.title = document.title;
                info.allButtons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t);
                info.divClasses = Array.from(document.querySelectorAll('div')).map(d => d.className).filter(c => c && c.length > 0 && c.length < 80).slice(0, 50);
                info.inputElements = Array.from(document.querySelectorAll('input')).map(i => ({type: i.type, placeholder: i.placeholder})).slice(0, 20);
                info.allSelects = Array.from(document.querySelectorAll('select, .el-select, .ant-select')).map((el, i) => ({
                    index: i,
                    className: el.className,
                    text: el.innerText.trim().substring(0, 50),
                    value: el.value || ''
                }));
                info.allTables = Array.from(document.querySelectorAll('table')).map((el, i) => ({
                    index: i,
                    className: el.className,
                    rowCount: el.querySelectorAll('tr').length
                }));
                return info;
            }
        """
        )
        sys.stdout.write(f"Page title: {page_info.get('title', 'N/A')}\n")
        sys.stdout.write(f"Buttons found: {page_info.get('allButtons', [])}\n")
        sys.stdout.write(f"Div classes (sample): {page_info.get('divClasses', [])}\n")
        sys.stdout.write(f"Input elements: {page_info.get('inputElements', [])}\n")
        sys.stdout.write(f"Select elements: {page_info.get('allSelects', [])}\n")
        sys.stdout.write(f"Table elements: {page_info.get('allTables', [])}\n")
        sys.stdout.flush()

        sys.stdout.write("\nStep 5: Try using '创建导出任务' button\n")
        sys.stdout.flush()

        try:
            logged_in_page.evaluate(
                """
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    for (const btn of buttons) {
                        const text = btn.innerText.trim();
                        if (text.includes('创建导出任务') && btn.offsetParent !== null) {
                            btn.click();
                            console.log('Clicked: ' + text);
                            break;
                        }
                    }
                }
            """
            )
            logged_in_page.wait_for_timeout(10000)

            sys.stdout.write("\nStep 5.1: Check for task creation result\n")
            sys.stdout.flush()
            result_info = logged_in_page.evaluate(
                """
                () => {
                    const info = {};
                    info.notifications = Array.from(document.querySelectorAll('.el-notification, .ant-notification, [class*="notification"], .el-message, .ant-message')).map(n => n.innerText.trim());
                    info.modalTitles = Array.from(document.querySelectorAll('.el-modal__title, .ant-modal-title')).map(t => t.innerText.trim());
                    info.allButtons = Array.from(document.querySelectorAll('button')).map(b => b.innerText.trim()).filter(t => t);
                    return info;
                }
            """
            )
            sys.stdout.write(f"Notifications: {result_info.get('notifications', [])}\n")
            sys.stdout.write(f"Modal titles: {result_info.get('modalTitles', [])}\n")
            sys.stdout.write(f"Buttons: {result_info.get('allButtons', [])}\n")
            sys.stdout.flush()

        except Exception as e:
            sys.stdout.write(f"Failed to create export task: {e}\n")
            sys.stdout.flush()

        sys.stdout.write("\nStep 6: Try realtime export\n")
        sys.stdout.flush()

        os.makedirs("downloads", exist_ok=True)
        before_files = set(os.listdir("downloads"))

        try:
            with logged_in_page.expect_download(timeout=300000) as download_info:
                sys.stdout.write("Waiting for download...\n")
                sys.stdout.flush()

                logged_in_page.evaluate(
                    """
                    () => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        for (const btn of buttons) {
                            const text = btn.innerText.trim();
                            if (text.includes('实时导出') && btn.offsetParent !== null) {
                                btn.click();
                                console.log('Clicked: ' + text);
                                break;
                            }
                        }
                    }
                """
                )

            download = download_info.value
            filename = download.suggested_filename
            file_path = f"downloads/{filename}"
            download.save_as(file_path)

            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

            sys.stdout.write(f"\nSUCCESS: Downloaded {filename} ({file_size} bytes)\n")
            sys.stdout.flush()

        except Exception as e:
            sys.stdout.write(f"\nexpect_download failed: {e}\n")
            sys.stdout.flush()

            # 后备方案：文件轮询检测
            sys.stdout.write("Trying file polling fallback...\n")
            sys.stdout.flush()
            logged_in_page.evaluate(
                """
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    for (const btn of buttons) {
                        const text = btn.innerText.trim();
                        if (text.includes('实时导出') && btn.offsetParent !== null) {
                            btn.click();
                            console.log('Polling click: ' + text);
                            break;
                        }
                    }
                }
            """
            )

            download_found = None
            for _ in range(120):
                time.sleep(1)
                current_files = set(os.listdir("downloads"))
                new_files = current_files - before_files
                if new_files:
                    download_found = os.path.join("downloads", list(new_files)[0])
                    break

            if download_found:
                file_size = os.path.getsize(download_found)
                sys.stdout.write(
                    f"\nSUCCESS: File polling found {os.path.basename(download_found)} ({file_size} bytes)\n"
                )
                sys.stdout.flush()
            else:
                sys.stdout.write("\nStep 6.1: Check for errors/notifications\n")
                sys.stdout.flush()
                error_info = logged_in_page.evaluate(
                    """
                    () => {
                        const info = {};
                        info.notifications = Array.from(document.querySelectorAll('.el-notification, .ant-notification, [class*="notification"], .el-message, .ant-message')).map(n => n.innerText.trim());
                        info.errors = Array.from(document.querySelectorAll('.el-form-item__error, .ant-form-item-explain, [class*="error"], .error-message')).map(e => e.innerText.trim());
                        info.alerts = Array.from(document.querySelectorAll('.el-alert, .ant-alert')).map(a => a.innerText.trim());
                        info.disabledButtons = Array.from(document.querySelectorAll('button[disabled]')).map(b => b.innerText.trim());
                        return info;
                    }
                """
                )
                sys.stdout.write(f"Notifications: {error_info.get('notifications', [])}\n")
                sys.stdout.write(f"Errors: {error_info.get('errors', [])}\n")
                sys.stdout.write(f"Alerts: {error_info.get('alerts', [])}\n")
                sys.stdout.write(f"Disabled buttons: {error_info.get('disabledButtons', [])}\n")
                sys.stdout.flush()
                pytest.fail(f"Download failed: {e}")

        sys.stdout.write("\n=== Test completed ===\n")
        sys.stdout.flush()

"""Test export download functionality."""

import os
import time

import pytest
from playwright.sync_api import Page

from modules.auto_test.pages.sales_order_export_page import SalesOrderExportPage

EXPORT_TEMPLATE = "！Dayone标准模板 --计算账单"


@pytest.mark.regression
@pytest.mark.ui
@pytest.mark.p1
class TestExportDownload:
    """Test export download functionality."""

    def test_export_download_simple(self, logged_in_page: Page) -> None:
        """Test simple export download."""
        export_page = SalesOrderExportPage(logged_in_page)

        print("\n=== Step 1: Navigate to export page ===")
        timestamp = str(int(time.time() * 1000))
        export_page.navigate_to(f"sales/order/exportPage?t={timestamp}&orderNo=")
        logged_in_page.wait_for_timeout(15000)

        print(f"URL: {export_page.current_url}")

        print("\n=== Step 2: Check export page structure ===")
        page_html = logged_in_page.evaluate(
            """
            () => {
                return document.body.innerHTML.substring(0, 5000);
            }
        """
        )
        print("Page HTML snippet (first 5000 chars):")
        print(page_html[:2000])

        print("\n=== Step 3: Check all buttons ===")
        buttons = logged_in_page.evaluate(
            """
            () => {
                const result = [];
                const btns = document.querySelectorAll('button');
                for (let i = 0; i < btns.length; i++) {
                    const text = btns[i].innerText.trim();
                    if (text) {
                        result.push({
                            index: i,
                            text: text,
                            className: btns[i].className,
                            id: btns[i].id || ''
                        });
                    }
                }
                return result;
            }
        """
        )
        print(f"Found {len(buttons)} buttons:")
        for btn in buttons:
            print(f"  [{btn['index']}] text='{btn['text']}', class={btn['className']}, id={btn['id']}")

        print("\n=== Step 4: Find and click real-time export button ===")
        realtime_btn_found = False
        for i, btn in enumerate(buttons):
            if "导出" in btn["text"]:
                print(f"\nFound export button: index={i}, text='{btn['text']}'")
                try:
                    logged_in_page.evaluate(
                        """
                        (index) => {
                            const btns = document.querySelectorAll('button');
                            if (btns[index]) {
                                btns[index].click();
                                return true;
                            }
                            return false;
                        }
                    """,
                        i,
                    )
                    realtime_btn_found = True
                    print(f"Clicked button index {i}")
                    break
                except Exception as e:
                    print(f"Failed to click button {i}: {e}")

        if realtime_btn_found:
            print("\n=== Step 5: Wait for download ===")
            try:
                with logged_in_page.expect_download(timeout=120000) as download_info:
                    print("Waiting for download...")

                download = download_info.value
                filename = download.suggested_filename
                os.makedirs("downloads", exist_ok=True)
                file_path = f"downloads/{filename}"
                download.save_as(file_path)

                file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

                print("\n✓ Download successful!")
                print(f"  Filename: {filename}")
                print(f"  File path: {file_path}")
                print(f"  File size: {file_size} bytes")
            except Exception as e:
                print(f"\n✗ Download failed: {e}")
        else:
            print("\n✗ No export button found")

        print("\n=== Test completed ===")

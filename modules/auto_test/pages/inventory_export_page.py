import os
import re
import time
from urllib.parse import unquote, urljoin

import allure
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class InventoryExportPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)

    @allure.step("等待导出页面加载")
    def wait_for_export_page(self, timeout: int = 30000) -> bool:
        try:
            start_time = time.time()
            while time.time() - start_time < timeout / 1000:
                if "exportPage" in self.page.url:
                    self._wait_for_export_content()
                    logger.info(f"当前页面已跳转到导出页面: {self.page.url}")
                    return True

                pages = self.page.context.pages
                for pg in pages:
                    if "exportPage" in pg.url:
                        self.page = pg
                        self._wait_for_export_content()
                        logger.info(f"已切换到导出页面: {pg.url}")
                        return True

                time.sleep(1)

            logger.warning(f"未找到导出页面，当前页面URL: {self.page.url}")
            return False
        except Exception as e:
            logger.warning(f"等待导出页面超时: {e}")
            return False

    @allure.step("检查是否在导出页面")
    def _wait_for_export_content(self, timeout: int = 15000) -> None:
        self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        self.page.wait_for_function(
            """
            () => Array.from(document.querySelectorAll('button')).some(button =>
                (button.textContent || '').includes('\\u5b9e\\u65f6\\u5bfc\\u51fa')
            ) || document.querySelectorAll('.el-checkbox, input[type="checkbox"], .tag_item').length > 0
            """,
            timeout=timeout,
        )

    def is_on_export_page(self) -> bool:
        return "exportPage" in self.page.url

    @allure.step("获取当前URL")
    def get_current_url(self) -> str:
        return self.page.url

    @allure.step("全选导出字段")
    def select_all_fields(self, fast_mode: bool = True) -> None:
        self.page.wait_for_timeout(500)

        if fast_mode:
            try:
                result = self._click_select_all_checkbox()
                logger.info("fast_mode 触发页面全选控件: {}", result)
                if result.get("clicked") or result.get("already_checked"):
                    self.page.wait_for_timeout(500)
                    if self.get_selected_field_count() > 0:
                        return
                    logger.warning("页面全选控件触发后未检测到已选字段，继续尝试逐项选择")
            except Exception as e:
                logger.warning("fast_mode 页面全选控件触发失败，继续尝试逐项选择: {}", e)

            try:
                result = self.page.evaluate(
                    """
                    () => {
                        const boxes = document.querySelectorAll('.el-checkbox:not(.is-checked)');
                        let count = 0;
                        for (const box of boxes) {
                            if (box.offsetParent !== null) {
                                box.click();
                                count++;
                            }
                        }
                        return { success: true, selected: count, total: boxes.length };
                    }
                """
                )
                logger.info("fast_mode 批量选择字段: {}", result)
                if self.get_selected_field_count() > 0:
                    return
                logger.warning("fast_mode 后未检测到已选字段，回退到逐个选择")
            except Exception as e:
                logger.warning("fast_mode JS 批量选择失败，回退到逐个选择: {}", e)

        select_all_selectors = [
            'button:has-text("全选")',
            'button:has-text("所有字段")',
            'button:has-text("全选/清空")',
            ".el-checkbox-group button",
            '//button[contains(text(),"选")]',
        ]

        for selector in select_all_selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.is_visible():
                    btn.click()
                    logger.info(f"点击{selector}按钮")
                    self.page.wait_for_timeout(500)
                    return
            except Exception:
                continue

        try:
            checkbox_count = self.page.locator('input[type="checkbox"]').count()
            logger.info(f"页面复选框数量: {checkbox_count}")

            step = 3 if fast_mode else 1
            limit = checkbox_count if fast_mode else min(30, checkbox_count)
            for i in range(0, limit, step):
                try:
                    checkbox = self.page.locator('input[type="checkbox"]').nth(i)
                    if not checkbox.is_checked():
                        checkbox.click()
                except Exception:
                    pass
            logger.info("已选择所有导出字段")
        except Exception as e:
            logger.warning(f"选择字段失败: {e}")

    @allure.step("清空已选导出字段")
    def _click_select_all_checkbox(self) -> dict:
        """通过导出页自身的“全选/清空”复选框选择字段，确保 Vue 状态同步。"""
        return self.page.evaluate(
            """
            () => {
                const isVisible = el => {
                    const style = window.getComputedStyle(el);
                    return el.offsetParent !== null && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const boxes = Array.from(document.querySelectorAll('.el-checkbox'))
                    .filter(box => isVisible(box));
                const selectAll = boxes.find(box => {
                    const text = (box.textContent || '').replace(/\\s+/g, '');
                    return text.includes('\\u5168\\u9009') || text.includes('\\u6e05\\u7a7a');
                });
                if (!selectAll) {
                    return { clicked: false, already_checked: false, reason: 'not_found', visible_boxes: boxes.length };
                }
                if (selectAll.classList.contains('is-checked')) {
                    return { clicked: false, already_checked: true, reason: 'already_checked', visible_boxes: boxes.length };
                }
                selectAll.click();
                return { clicked: true, already_checked: false, text: selectAll.textContent.trim(), visible_boxes: boxes.length };
            }
            """
        )

    @allure.step("清空已选导出字段")
    def deselect_all_fields(self) -> None:
        self.page.wait_for_timeout(500)
        clear_selectors = ['button:has-text("清空")', 'button:has-text("全选/清空")']
        for selector in clear_selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.is_visible():
                    btn.click()
                    self.page.wait_for_timeout(500)
                    logger.info(f"点击{selector}清空按钮")
                    return
            except Exception:
                continue
        try:
            result = self.page.evaluate(
                """
                () => {
                    const checked = Array.from(document.querySelectorAll('input[type="checkbox"]:checked'))
                        .filter(input => !input.disabled);
                    let count = 0;
                    for (const input of checked) {
                        const label = input.closest('label') || input;
                        label.click();
                        count++;
                    }
                    return { cleared: count, remaining: document.querySelectorAll('input[type="checkbox"]:checked').length };
                }
                """
            )
            logger.info("已清空可取消的导出字段: {}", result)
            return
        except Exception:
            pass
        try:
            checked = self.page.locator('input[type="checkbox"]:checked').all()
            for cb in checked:
                cb.click(force=True)
            logger.info("已清空所有字段")
        except Exception as e:
            logger.warning(f"清空字段失败: {e}")

    @allure.step("选择指定字段: {field_name}")
    def select_field(self, field_name: str) -> bool:
        try:
            result = self.page.evaluate(
                """
                (fieldName) => {
                    const normalize = value => (value || '').replace(/\\s+/g, '').toLowerCase();
                    const target = normalize(fieldName);
                    const aliases = {
                        'sku编码': ['sku编码', 'sku'],
                        '产品名称': ['产品名称', '商品名称'],
                        '产品图片': ['产品图片', '商品图片'],
                        '库存总量': ['库存总量', '总可用库存'],
                        '未发货数量': ['未发货数量', '未发货数'],
                        '在途数量': ['在途数量', '在途量'],
                        '7天销售': ['7天销量', '7天销售']
                    };
                    const candidates = (aliases[fieldName] || [fieldName]).map(normalize);
                    const boxes = Array.from(document.querySelectorAll('.el-checkbox, label, .tag_item'))
                        .filter(box => {
                            const rect = box.getBoundingClientRect();
                            const style = window.getComputedStyle(box);
                            return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                        });
                    for (const box of boxes) {
                        const text = normalize(box.textContent);
                        if (!text || (!candidates.some(candidate => text.includes(candidate)) && !text.includes(target))) {
                            continue;
                        }
                        const input = box.querySelector('input[type="checkbox"]');
                        const isChecked = box.classList.contains('is-checked') || (input && input.checked);
                        if (!isChecked) {
                            const clickable = box.querySelector('.el-checkbox__input, input[type="checkbox"]') || box;
                            clickable.click();
                        }
                        return { selected: true, text: box.textContent.trim(), already_checked: isChecked };
                    }
                    return { selected: false, visibleTexts: boxes.slice(0, 120).map(box => box.textContent.trim()) };
                }
                """,
                field_name,
            )
            if result.get("selected"):
                self.page.wait_for_timeout(300)
                logger.info("宸查€夋嫨瀛楁: {} -> {}", field_name, result)
                return True
            field_label = self.page.locator(f'.el-checkbox__label:has-text("{field_name}")').first
            if field_label.count() > 0:
                field_label.click(force=True)
                self.page.wait_for_timeout(300)
                logger.info(f"已选择字段: {field_name}")
                return True
            else:
                logger.warning(f"未找到字段: {field_name}")
                return False
        except Exception as e:
            logger.warning(f"选择字段{field_name}失败: {e}")
            return False

    @allure.step("批量选择导出字段")
    def select_fields(self, field_names: list[str]) -> int:
        selected = 0
        for field_name in field_names:
            if self.select_field(field_name):
                selected += 1
        logger.info(f"批量选择字段完成: {selected}/{len(field_names)}")
        return selected

    @allure.step("选择首个可用导出模板")
    def select_first_template_if_available(self) -> bool:
        try:
            clicked = self.page.evaluate(
                """() => {
                    const selects = Array.from(document.querySelectorAll('.el-select, .ant-select'));
                    const target = selects.find(select => {
                        const text = (select.textContent || '').trim();
                        const input = select.querySelector('input');
                        const placeholder = input ? (input.getAttribute('placeholder') || '') : '';
                        return (text.includes('模板') || placeholder.includes('模板')) && select.offsetParent !== null;
                    });
                    if (!target) return false;
                    target.click();
                    return true;
                }"""
            )
            if not clicked:
                return False

            self.page.wait_for_timeout(500)
            selected = self.page.evaluate(
                """() => {
                    const ignored = new Set(['calibri', '微软雅黑', 'arial', 'times new roman', '宋体']);
                    const items = Array.from(document.querySelectorAll('.el-select-dropdown__item, .ant-select-item-option'))
                        .filter(item => item.offsetParent !== null);
                    const item = items.find(item => {
                        const text = (item.textContent || '').trim();
                        return text && !ignored.has(text.toLowerCase()) && !/^[0-9]+\\s*条\\s*\\/\\s*页$/.test(text);
                    });
                    if (!item) return false;
                    item.click();
                    return true;
                }"""
            )
            logger.info("选择首个可用导出模板: {}", selected)
            return bool(selected)
        except Exception as e:
            logger.warning("选择导出模板失败: {}", e)
            return False

    @allure.step("获取导出字段列表")
    def get_export_fields(self) -> list:
        fields = []
        field_items = self.page.locator(".el-checkbox, .el-checkbox__label, label").all()
        for item in field_items[:50]:
            try:
                text = item.text_content() or ""
                text = text.strip()
                if text and len(text) > 1 and len(text) < 50:
                    fields.append(text)
            except Exception:
                pass
        logger.info(f"导出字段列表: {fields[:10]}...")
        return fields

    @allure.step("获取已选字段数量")
    def get_selected_field_count(self) -> int:
        try:
            tag_count = self.page.locator(".tag_item").count()
            if tag_count > 0:
                return tag_count
            count = self.page.locator('input[type="checkbox"]:checked').count()
            return count
        except Exception:
            return 0

    @allure.step("获取总字段数量")
    def get_total_field_count(self) -> int:
        try:
            count = self.page.locator('input[type="checkbox"]').count()
            return count
        except Exception:
            return 0

    @allure.step("点击实时导出按钮")
    def click_realtime_export(self) -> None:
        export_button = self.page.get_by_role("button", name="实时导出", exact=True)
        if export_button.count() == 0:
            raise ValueError("未找到可见的实时导出按钮")
        if not export_button.first.is_enabled():
            raise ValueError("实时导出按钮不可用，请检查导出字段是否已选择")
        export_button.first.click(timeout=10000)
        logger.info("点击实时导出按钮")

    def _js_click_realtime_export(self) -> None:
        clicked = self.page.evaluate(
            """() => {
                const buttons = Array.from(document.querySelectorAll('button'));
                const button = buttons.find(btn => (btn.textContent || '').trim() === '实时导出'
                    && !btn.disabled && btn.offsetParent !== null);
                if (!button) return false;
                button.click();
                return true;
            }"""
        )
        if not clicked:
            raise ValueError("未找到可用的实时导出按钮")
        logger.info("通过JS点击实时导出按钮")

    @allure.step("点击非实时导出按钮")
    def click_async_export(self) -> None:
        self.page.wait_for_timeout(1000)
        export_btns = self.page.locator('button:has-text("非实时导出")').all()
        if export_btns:
            export_btns[0].click()
            logger.info("点击非实时导出按钮")
        else:
            logger.warning("未找到非实时导出按钮")

    @allure.step("等待导出下载")
    def wait_for_download(self, timeout: int = 60000) -> dict:
        try:
            with self.page.expect_download(timeout=timeout) as download_info:
                logger.info("等待文件下载...")
                self.click_realtime_export()

            download = download_info.value
            filename = download.suggested_filename
            os.makedirs("downloads", exist_ok=True)
            file_path = f"downloads/{filename}"
            download.save_as(file_path)

            file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0

            result = {
                "success": True,
                "filename": filename,
                "file_path": file_path,
                "file_size": file_size,
                "url": download.url,
            }
            logger.info(f"导出下载成功: {filename}, 大小: {file_size}字节")
            return result
        except Exception as e:
            logger.warning(f"导出下载超时或失败: {e}")
            return {"success": False, "error": str(e), "filename": None, "file_path": None, "file_size": 0, "url": None}

    @allure.step("下载到指定路径: {save_path}")
    def download_to(self, save_path: str, timeout: int = 60000) -> dict:
        download_dir = os.path.dirname(save_path)
        os.makedirs(download_dir, exist_ok=True)
        file_responses = []
        export_response_objects = []
        export_responses = []

        def capture_file_response(response) -> None:
            headers = response.headers
            content_type = headers.get("content-type", "").lower()
            disposition = headers.get("content-disposition", "").lower()
            if "attachment" in disposition or any(
                marker in content_type for marker in ("spreadsheet", "excel", "octet-stream")
            ):
                file_responses.append(response)
            if "export" in response.url.lower():
                export_response_objects.append(response)
                export_responses.append(
                    {"url": response.url, "status": response.status, "content_type": content_type}
                )

        self.page.on("response", capture_file_response)
        try:
            logger.info("实时导出前页面状态: {}", self._get_export_page_state())
            try:
                with self.page.expect_download(timeout=min(timeout, 5000)) as download_info:
                    self.click_realtime_export()
            except Exception:
                if file_responses or export_response_objects:
                    raise
                with self.page.expect_download(timeout=min(timeout, 5000)) as download_info:
                    self._js_click_realtime_export()

            download = download_info.value
            filename = download.suggested_filename
            download.save_as(save_path)

            file_size = os.path.getsize(save_path) if os.path.exists(save_path) else 0

            return {
                "success": True,
                "filename": filename,
                "file_path": save_path,
                "file_size": file_size,
                "url": download.url,
            }
        except Exception as e:
            if file_responses:
                response = file_responses[-1]
                disposition = response.headers.get("content-disposition", "")
                filename_match = re.search(r"filename\*?=(?:UTF-8''|[\"']?)([^;\"']+)", disposition, re.I)
                filename = unquote(filename_match.group(1)) if filename_match else os.path.basename(save_path)
                with open(save_path, "wb") as export_file:
                    export_file.write(response.body())
                file_size = os.path.getsize(save_path)
                logger.info("从实时导出响应保存文件: {}, 大小: {}字节", filename, file_size)
                return {
                    "success": file_size > 0,
                    "filename": filename,
                    "file_path": save_path,
                    "file_size": file_size,
                    "url": response.url,
                }

            if export_response_objects:
                response = export_response_objects[-1]
                try:
                    payload = response.json()
                except Exception:
                    payload = None

                download_url = self._find_download_url(payload.get("data") if isinstance(payload, dict) else payload)
                if download_url:
                    absolute_url = urljoin(response.url, download_url)
                    api_response = self.page.context.request.get(absolute_url)
                    if api_response.ok:
                        disposition = api_response.headers.get("content-disposition", "")
                        filename_match = re.search(r"filename\*?=(?:UTF-8''|[\"']?)([^;\"']+)", disposition, re.I)
                        filename = (
                            unquote(filename_match.group(1))
                            if filename_match
                            else os.path.basename(download_url.split("?", 1)[0]) or os.path.basename(save_path)
                        )
                        with open(save_path, "wb") as export_file:
                            export_file.write(api_response.body())
                        file_size = os.path.getsize(save_path)
                        return {
                            "success": file_size > 0,
                            "filename": filename,
                            "file_path": save_path,
                            "file_size": file_size,
                            "url": absolute_url,
                        }

            api_result = self._download_inventory_export_via_api(save_path, timeout)
            if api_result["success"]:
                logger.info("通过实时导出接口保存文件成功: {}", api_result)
                return api_result
            logger.warning("实时导出接口兜底未成功: {}", api_result)

            messages = self.page.locator(
                ".el-message:visible, .el-notification:visible, [role='alert']:visible"
            ).all_text_contents()
            logger.warning("实时导出未产生文件，页面提示: {}，导出响应: {}", messages, export_responses[-10:])
            return {
                "success": False,
                "error": api_result.get("error") or str(e),
                "filename": None,
                "file_path": None,
                "file_size": 0,
                "url": None,
                "messages": messages,
                "export_responses": export_responses[-10:],
            }
        finally:
            self.page.remove_listener("response", capture_file_response)

    def _get_export_page_state(self) -> dict:
        return self.page.evaluate(
            """
            () => ({
                url: location.href,
                sku_count: document.querySelectorAll('.text.item').length,
                selected_tag_count: document.querySelectorAll('.tag_item').length,
                checked_count: document.querySelectorAll('input[type="checkbox"]:checked').length,
                realtime_button_count: Array.from(document.querySelectorAll('button'))
                    .filter(button => (button.textContent || '').includes('\\u5b9e\\u65f6\\u5bfc\\u51fa')).length,
                api_urls: Array.from(performance.getEntriesByType('resource'))
                    .map(entry => entry.name)
                    .filter(name => name.includes('/oms-admin/'))
                    .slice(-10),
                alerts: Array.from(document.querySelectorAll('.el-message, .el-notification, [role="alert"]'))
                    .filter(el => el.offsetParent !== null)
                    .map(el => (el.textContent || '').trim()),
                vue_state: (() => {
                    const nodes = Array.from(document.querySelectorAll('*'));
                    for (const node of nodes) {
                        let component = node.__vueParentComponent;
                        while (component) {
                            const setup = component.setupState || {};
                            if ('d' in setup && 'D' in setup) {
                                return {
                                    keys: Object.keys(setup),
                                    selected_columns: Array.isArray(setup.d) ? setup.d.length : null,
                                    item_ids: Array.isArray(setup.D) ? setup.D.length : null
                                };
                            }
                            component = component.parent;
                        }
                    }
                    return null;
                })()
            })
            """
        )

    def _download_inventory_export_via_api(self, save_path: str, timeout: int) -> dict:
        """使用当前登录态调用库存 SKU 实时导出接口，兜底验证真实导出链路。"""
        try:
            origin_match = re.match(r"^https?://[^/]+", self.page.url)
            if not origin_match:
                return {"success": False, "error": "无法识别导出页域名", "filename": None, "file_path": None, "file_size": 0, "url": None}
            origin = origin_match.group(0)
            api_base = self._get_inventory_api_base(origin)
            item_ids = self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('.el-col-5 .text.item'))
                    .map(item => (item.textContent || '').trim())
                    .filter(Boolean)
                """
            )
            if not item_ids:
                return {"success": False, "error": "导出页未读取到 SKU 列表", "filename": None, "file_path": None, "file_size": 0, "url": None}
            if len(item_ids) > 20:
                logger.info("实时导出接口兜底按当前页验证，SKU 数量由 {} 缩小到 20", len(item_ids))
                item_ids = item_ids[:20]
            token = self.page.evaluate("() => localStorage.getItem('Admin-Token')")
            headers = {"Admin-Token": token, "Authorization": f"Bearer {token}"} if token else {}

            columns_response = self.page.context.request.get(
                f"{api_base}/base/inventory/getExportColumnInfo",
                headers=headers,
                timeout=timeout,
            )
            if not columns_response.ok:
                return {
                    "success": False,
                    "error": f"导出字段接口失败: {columns_response.status}",
                    "filename": None,
                    "file_path": None,
                    "file_size": 0,
                    "url": None,
                }

            columns_payload = columns_response.json()
            if not isinstance(columns_payload, dict):
                return {
                    "success": False,
                    "error": f"导出字段接口返回异常: status={columns_response.status}, body={columns_response.text()[:500]}",
                    "filename": None,
                    "file_path": None,
                    "file_size": 0,
                    "url": None,
                }
            data = columns_payload.get("data") if isinstance(columns_payload, dict) else {}
            if not isinstance(data, dict):
                return {
                    "success": False,
                    "error": f"导出字段接口未返回字段数据: {columns_payload}",
                    "filename": None,
                    "file_path": None,
                    "file_size": 0,
                    "url": None,
                }
            check_columns = []
            for group_name in ("OmsInventory", "OmsLocation"):
                for column in data.get(group_name, []) or []:
                    check_columns.append(column)
            selected_labels = self.page.evaluate(
                """
                () => Array.from(document.querySelectorAll('.tag_item'))
                    .map(tag => (tag.textContent || '').replace(/^\\s*\\d+\\s*/, '').trim())
                    .filter(Boolean)
                """
            )
            if selected_labels and len(selected_labels) < len(check_columns):
                selected_text = "\n".join(selected_labels)
                filtered_columns = [
                    column for column in check_columns if str(column.get("label", "")).strip() in selected_text
                ]
                if filtered_columns:
                    check_columns = filtered_columns
            if not check_columns:
                return {"success": False, "error": "导出字段接口未返回字段", "filename": None, "file_path": None, "file_size": 0, "url": None}

            export_response = self.page.context.request.post(
                f"{api_base}/base/inventory/inventoryExport",
                data={"checkColumns": check_columns, "itemIds": item_ids},
                headers=headers,
                timeout=timeout,
            )
            if not export_response.ok:
                return {
                    "success": False,
                    "error": f"实时导出接口失败: {export_response.status}",
                    "filename": None,
                    "file_path": None,
                    "file_size": 0,
                    "url": None,
                }

            content_type = export_response.headers.get("content-type", "").lower()
            disposition = export_response.headers.get("content-disposition", "")
            body = export_response.body()
            source_url = export_response.url

            if "application/json" in content_type:
                payload = export_response.json()
                download_url = self._find_download_url(payload.get("data") if isinstance(payload, dict) else payload)
                if not download_url:
                    return {
                        "success": False,
                        "error": f"实时导出接口未返回文件: {payload}",
                        "filename": None,
                        "file_path": None,
                        "file_size": 0,
                        "url": None,
                    }
                source_url = urljoin(export_response.url, download_url)
                file_response = self.page.context.request.get(source_url, headers=headers, timeout=timeout)
                if not file_response.ok:
                    return {"success": False, "error": f"导出文件下载失败: {file_response.status}", "filename": None, "file_path": None, "file_size": 0, "url": source_url}
                disposition = file_response.headers.get("content-disposition", "")
                body = file_response.body()

            filename_match = re.search(r"filename\*?=(?:UTF-8''|[\"']?)([^;\"']+)", disposition, re.I)
            filename = unquote(filename_match.group(1)) if filename_match else os.path.basename(save_path)
            with open(save_path, "wb") as export_file:
                export_file.write(body)
            file_size = os.path.getsize(save_path)
            return {
                "success": file_size > 0,
                "filename": filename,
                "file_path": save_path,
                "file_size": file_size,
                "url": source_url,
            }
        except Exception as api_error:
            logger.warning("实时导出接口兜底失败: {}", api_error)
            return {"success": False, "error": str(api_error), "filename": None, "file_path": None, "file_size": 0, "url": None}

    def _get_inventory_api_base(self, origin: str) -> str:
        api_urls = self.page.evaluate(
            """
            () => Array.from(performance.getEntriesByType('resource'))
                .map(entry => entry.name)
                .filter(name => name.includes('/oms-admin/base/inventory/getExportColumnInfo'))
            """
        )
        if api_urls:
            return api_urls[-1].split("/base/inventory/getExportColumnInfo", 1)[0]
        return f"{origin}/oms-api/oms-admin"

    def _find_download_url(self, value) -> str | None:
        if isinstance(value, str) and (value.startswith(("http://", "https://", "/")) or ".xlsx" in value.lower()):
            return value
        if isinstance(value, dict):
            for key in ("downloadUrl", "fileUrl", "url", "path"):
                if key in value:
                    found = self._find_download_url(value[key])
                    if found:
                        return found
            for nested in value.values():
                found = self._find_download_url(nested)
                if found:
                    return found
        return None

    @allure.step("获取导出页面标题")
    def get_page_title(self) -> str:
        title = self.page.title()
        return title if title else ""

    @allure.step("检查是否有导出结果")
    def has_export_results(self) -> bool:
        self.page.wait_for_timeout(2000)
        no_data = self.page.locator('span:has-text("暂无数据"), div:has-text("暂无数据")')
        if no_data.count() > 0:
            logger.info("导出页面显示暂无数据")
            return False
        return True

    @allure.step("选择导出模板")
    def select_template(self, template_name: str) -> bool:
        try:
            template_input = self.page.locator('input[placeholder*="选择模板"]').first
            if template_input.count() > 0:
                template_input.click(force=True)
                self.page.wait_for_timeout(500)
                option = self.page.locator(f'.el-select-dropdown__item:has-text("{template_name}")').first
                if option.count() > 0:
                    option.click(force=True)
                    logger.info(f"已选择模板: {template_name}")
                    return True
            return False
        except Exception as e:
            logger.warning(f"选择模板失败: {e}")
            return False

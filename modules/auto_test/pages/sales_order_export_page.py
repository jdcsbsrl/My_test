import os
import re
import time
import uuid
from urllib.parse import unquote, urljoin

import allure
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()

# Canonical product template name. The selector implementation remains tolerant
# of legacy spelling variants, while callers use one stable value.
EXPORT_TEMPLATE = "！Dayone标准模板 --计算账单"


class SalesOrderExportPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.export_url_pattern = "sales/order/exportPage"

    @allure.step("等待导出页面加载")
    def wait_for_export_page(self, timeout: int = 30000) -> bool:
        try:
            start_time = time.time()
            while time.time() - start_time < timeout / 1000:
                if self.export_url_pattern in self.page.url:
                    self.wait_for_page_settle(timeout=5000)
                    if self._export_controls_ready():
                        logger.info("导出页面已跳转且业务控件已挂载")
                        return True

                pages = self.page.context.pages
                for pg in pages:
                    if self.export_url_pattern in pg.url:
                        self.page = pg
                        self.wait_for_page_settle(timeout=5000)
                        if self._export_controls_ready():
                            logger.info("已切换到导出页面且业务控件已挂载")
                            return True

                if int(time.time() - start_time) % 5 == 0:
                    pages_info = [{"url": pg.url, "title": pg.title()} for pg in pages]
                    logger.info(
                        "当前所有页面: {}",
                        [{**item, "url": self._redact_url(item["url"])} for item in pages_info],
                    )
                    logger.info("当前页面URL: {}, 标题: {}", self._redact_url(self.page.url), self.page.title())

                self.wait_for_poll_interval(1000)

            pages_info = [{"url": pg.url, "title": pg.title()} for pg in pages]
            logger.warning(
                "超时，所有页面: {}",
                [{**item, "url": self._redact_url(item["url"])} for item in pages_info],
            )
            logger.warning("未找到导出页面，当前页面URL: {}", self._redact_url(self.page.url))
            return False
        except Exception as e:
            logger.warning(f"等待导出页面超时: {e}")
            return False

    def _export_controls_ready(self) -> bool:
        """Return true only after the export SPA has mounted its real controls.

        Checking body text is insufficient here: the route can be ready while
        the Vue application is still loading its template/field data.
        """
        try:
            template_select = self.page.locator(
                '.el-select:visible, .ant-select:visible'
            )
            realtime_button = self.page.get_by_role("button", name="实时导出", exact=True)
            return template_select.count() > 0 or realtime_button.count() > 0
        except Exception:
            return False

    @allure.step("检查是否在导出页面")
    def is_on_export_page(self) -> bool:
        return self.export_url_pattern in self.page.url

    @allure.step("获取当前URL")
    def get_current_url(self) -> str:
        return self.page.url

    @allure.step("全选导出字段")
    def select_all_fields(self, fast_mode: bool = False) -> None:
        self.wait_for_loading_complete(timeout=10000)

        if fast_mode:
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
                return
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
                    self.wait_for_loading_complete(timeout=10000)
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
    def deselect_all_fields(self) -> None:
        self.wait_for_loading_complete(timeout=10000)
        clear_selectors = ['button:has-text("清空")', 'button:has-text("全选/清空")']
        for selector in clear_selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.is_visible():
                    btn.click()
                    self.wait_for_loading_complete(timeout=10000)
                    logger.info(f"点击{selector}清空按钮")
                    return
            except Exception:
                continue
        try:
            checked = self.page.locator('input[type="checkbox"]:checked').all()
            for cb in checked:
                cb.click(force=True)
            logger.info("已清空所有字段")
        except Exception as e:
            logger.warning(f"清空字段失败: {e}")

    @allure.step("选择指定字段: {field_name}")
    def select_field(self, field_name: str) -> bool:
        # 多选择器回退策略
        selectors = [
            f'.el-checkbox__label:has-text("{field_name}")',
            f'.ant-checkbox-wrapper:has-text("{field_name}")',
            f'label:has-text("{field_name}")',
            f'//label[contains(text(), "{field_name}")]',
            f'//span[contains(text(), "{field_name}")]/preceding-sibling::span/input[@type="checkbox"]',
            f'//span[contains(text(), "{field_name}")]/..//input[@type="checkbox"]',
        ]

        for selector in selectors:
            try:
                el = self.page.locator(selector).first
                if el.count() > 0 and el.is_visible():
                    if el.get_attribute("type") == "checkbox":
                        if not el.is_checked():
                            el.check(force=True)
                    else:
                        el.click(force=True)
                    self.wait_for_loading_complete(timeout=10000)
                    logger.info(f"已选择字段: {field_name} (通过选择器: {selector[:50]}...)")
                    return True
            except Exception:
                continue

        # JS回退：通过文本查找并点击复选框标签
        try:
            result = self.page.evaluate(
                f"""
                () => {{
                    const target = '{field_name}';
                    const labels = document.querySelectorAll('label, span, .el-checkbox__label, .ant-checkbox-wrapper > span');
                    for (const label of labels) {{
                        if (label.textContent.trim() === target || label.textContent.trim().includes(target)) {{
                            const clickable = label.querySelector('input[type="checkbox"]') || label.closest('.el-checkbox') || label.closest('.ant-checkbox-wrapper') || label;
                            if (clickable) {{
                                clickable.click();
                                return true;
                            }}
                        }}
                    }}
                    // 尝试通过span文本找checkbox
                    const allSpans = document.querySelectorAll('span');
                    for (const span of allSpans) {{
                        if (span.textContent.trim() === target || span.textContent.trim().includes(target)) {{
                            const parent = span.closest('.el-checkbox') || span.closest('.ant-checkbox-wrapper');
                            if (parent) {{
                                parent.click();
                                return true;
                            }}
                            const checkbox = parent.querySelector('input[type="checkbox"]');
                            if (checkbox) {{
                                checkbox.click();
                                return true;
                            }}
                        }}
                    }}
                    return false;
                }}
            """
            )
            if result:
                self.wait_for_loading_complete(timeout=10000)
                logger.info(f"已选择字段: {field_name} (通过JS回退)")
                return True
        except Exception as e:
            logger.warning(f"JS回退选择字段{field_name}失败: {e}")

        logger.warning(f"未找到字段: {field_name}")
        return False

    @allure.step("批量选择导出字段")
    def select_fields(self, field_names: list[str]) -> int:
        selected = 0
        for field_name in field_names:
            if self.select_field(field_name):
                selected += 1
        logger.info(f"批量选择字段完成: {selected}/{len(field_names)}")
        return selected

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
            count = self.page.locator('input[type="checkbox"]:checked').count()
            return count
        except Exception:
            return 0

    @allure.step("确保导出字段已选择: {field_name}")
    def ensure_field_selected(self, field_name: str) -> bool:
        return self.select_field(field_name)

    @allure.step("获取总字段数量")
    def get_total_field_count(self) -> int:
        try:
            count = self.page.locator('input[type="checkbox"]').count()
            return count
        except Exception:
            return 0

    @allure.step("选择导出模板: {template_name}")
    def select_export_template(self, template_name: str) -> bool:
        try:
            self.wait_for_page_settle(timeout=30000)

            template_variants = [
                template_name,
                template_name.replace(" --", "-"),
                template_name.replace("-", "--"),
            ]

            # 1. 先点击空白处关闭任何已打开的下拉菜单
            self.page.locator("body").click()
            self.wait_for_loading_complete(timeout=10000)

            # 2. 精确找到"请选择导出模板"所在的选择器
            #    使用 XPath 定位包含"请选择导出模板"文本的 el-select 元素
            selectors = [
                '//div[contains(@class, "el-select") and .//span[contains(text(), "请选择导出模板")]]',
                '//div[contains(@class, "el-select__selected-item") and .//span[contains(text(), "请选择导出模板")]]',
                '//div[contains(@class, "el-select") and .//span[@class="el-select__placeholder"]]',
                ".el-select:nth-child(2)",
                '.ant-select:has-text("请选择导出模板")',
                ".el-select",
                ".ant-select",
            ]

            clicked = False
            for selector in selectors:
                try:
                    el = self.page.locator(selector).first
                    if el.count() > 0 and el.is_visible():
                        el.click()
                        clicked = True
                        logger.info(f"点击模板选择器: {selector}")
                        break
                except Exception:
                    continue

            if not clicked:
                logger.warning("未找到模板选择器")

            # 回退方案：通过 JavaScript 直接查找并点击模板选择器
            if not clicked:
                try:
                    result = self.page.evaluate(
                        """
                        () => {
                            const debug = {};
                            debug.selectCount = document.querySelectorAll('.el-select').length;
                            debug.selectTexts = Array.from(document.querySelectorAll('.el-select')).map((el, i) => ({index: i, text: el.innerText.trim(), className: el.className}));
                            debug.allSelectDropdownItems = Array.from(document.querySelectorAll('.el-select-dropdown__item')).map(el => el.textContent.trim());
                            debug.pageUrl = window.location.href;
                            debug.pageTitle = document.title;

                            const selects = document.querySelectorAll('.el-select');
                            for (let i = 0; i < selects.length; i++) {
                                const text = selects[i].innerText.trim();
                                if (text.includes('请选择导出模板')) {
                                    selects[i].click();
                                    debug.clicked = i;
                                    debug.clickedText = text;
                                    return { success: true, debug: debug };
                                }
                            }
                            if (selects.length > 1) {
                                selects[1].click();
                                debug.clickedFallback = 1;
                                debug.clickedText = selects[1].innerText.trim();
                                return { success: true, debug: debug };
                            }
                            return { success: false, debug: debug };
                        }
                    """
                    )
                    clicked = result.get("success", False)
                    debug_info = result.get("debug", {})
                    logger.info(f"模板选择器调试 - select数量: {debug_info.get('selectCount')}")
                    logger.info(f"模板选择器调试 - select内容: {debug_info.get('selectTexts', [])}")
                    logger.info(f"模板选择器调试 - 下拉项: {debug_info.get('allSelectDropdownItems', [])}")
                    logger.info(
                        f"模板选择器调试 - URL: {debug_info.get('pageUrl')}, 标题: {debug_info.get('pageTitle')}"
                    )
                    if clicked:
                        logger.info(
                            f"通过JS evaluate点击模板选择器成功: {debug_info.get('clicked', debug_info.get('clickedFallback'))}"
                        )
                except Exception as e:
                    logger.warning(f"JS evaluate点击模板选择器失败: {e}")

            if not clicked:
                return False

            self.wait_for_page_settle(timeout=30000)

            # The selector can render before the async template request has
            # populated its options. Wait for an actual visible option.
            visible_items = self.page.locator(".el-select-dropdown__item:visible")
            try:
                visible_items.first.wait_for(state="visible", timeout=30000)
            except Exception:
                logger.warning("模板下拉已打开但选项未在限定时间内出现")

            # 3. 获取下拉选项并验证
            items = visible_items.all()
            logger.info(f"下拉选项数量: {len(items)}")
            for item in items:
                text = item.text_content() or ""
                logger.info(f"下拉选项内容: {text}")

            # 4. 过滤掉字体名称（如 Calibri, 微软雅黑 等），只保留模板选项
            font_names = {"calibri", "微软雅黑", "arial", "times new roman", "宋体"}

            js_clicked = self.page.evaluate(
                """
                ({variants, fonts}) => {
                    const items = Array.from(document.querySelectorAll('.el-select-dropdown__item'))
                        .filter(item => item.offsetParent !== null);
                    const target = items.find(item => {
                        const text = (item.textContent || '').trim();
                        return text && !fonts.includes(text.toLowerCase())
                            && variants.some(name => text.includes(name) || name.includes(text));
                    });
                    if (!target) return false;
                    target.click();
                    return true;
                }
                """,
                {"variants": template_variants, "fonts": list(font_names)},
            )
            if js_clicked:
                logger.info("成功选择模板: {}", template_name)
                self.wait_for_loading_complete(timeout=10000)
                return True

            # 先尝试精确匹配
            for name_variant in template_variants:
                for item in items:
                    try:
                        text = (item.text_content() or "").strip()
                        if not text or text.lower() in font_names:
                            continue
                        if name_variant in text or text in name_variant:
                            item.click()
                            logger.info(f"成功选择模板: {text}")
                            self.wait_for_loading_complete(timeout=10000)
                            return True
                    except Exception:
                        continue

            # 精确匹配失败时，使用关键字模糊匹配作为后备方案
            # 去除所有空白字符后匹配，避免隐藏字符/不同空白编码的影响
            keywords = ["dayone", "标准模板", "计算账单"]
            for item in items:
                try:
                    text = (item.text_content() or "").strip()
                    if not text or text.lower() in font_names:
                        continue
                    # 移除所有空白和特殊字符，仅保留中文和字母数字
                    import re

                    text_clean = re.sub(r"[\s\u200b-\u200d\uFEFF\xa0]+", "", text).lower()
                    if all(kw in text_clean for kw in keywords):
                        item.click()
                        logger.info(f"模糊匹配成功（归一化后），选择模板: {text}")
                        self.wait_for_loading_complete(timeout=10000)
                        return True
                except Exception:
                    continue

            # 最后兜底方案：JS直接点击下拉项
            logger.info("尝试JS兜底选择模板...")
            try:
                js_clicked = self.page.evaluate(
                    """
                    (name) => {
                        const items = document.querySelectorAll('.el-select-dropdown__item');
                        for (const item of items) {
                            const text = item.textContent || '';
                            if (text.includes('Dayone') && text.includes('标准模板')) {
                                item.click();
                                return true;
                            }
                        }
                        return false;
                    }
                """,
                    template_name,
                )
                if js_clicked:
                    logger.info("JS兜底选择模板成功")
                    self.wait_for_loading_complete(timeout=10000)
                    return True
            except Exception as e:
                logger.warning(f"JS兜底选择模板失败: {e}")

            logger.warning(f"未找到模板 '{template_name}', 尝试了变体: {template_variants}")
            return False

        except Exception as e:
            logger.warning(f"选择模板失败: {e}")
            return False

    @allure.step("获取当前选中的模板")
    def get_selected_template(self) -> str | None:
        try:
            template_input = self.page.locator('input[placeholder*="选择导出模板"]').first
            if template_input.count() > 0:
                return template_input.input_value()
            return None
        except Exception as e:
            logger.warning(f"获取选中模板失败: {e}")
            return None

    @allure.step("点击实时导出按钮")
    def click_realtime_export(self) -> None:
        export_button = self.page.get_by_role("button", name="实时导出", exact=True)
        export_button.first.wait_for(state="visible", timeout=30000)
        if not export_button.first.is_enabled():
            raise ValueError("实时导出按钮不可用，请检查导出字段是否已选择")
        logger.info(
            "实时导出按钮: count={}, enabled={}",
            export_button.count(),
            export_button.first.is_enabled(),
        )
        export_button.first.click(timeout=10000)
        logger.info("已点击实时导出按钮")

    @allure.step("等待导出下载")
    def wait_for_download(self, timeout: int = 120000) -> dict:
        """监听实时导出直接触发的浏览器下载事件。"""
        download_dir = ".runtime/downloads"
        os.makedirs(download_dir, exist_ok=True)
        file_responses = []
        export_responses = []
        export_response_objects = []

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
            logger.info("等待文件下载（浏览器事件监听）...")
            # Respect the caller's timeout; CI exports can exceed 30 seconds.
            with self.page.expect_download(timeout=timeout) as download_info:
                self.click_realtime_export()

            download = download_info.value
            filename = self._safe_artifact_name(download.suggested_filename, default="sales_order_export.xlsx")
            file_path = self._runtime_artifact_path("downloads", f"{uuid.uuid4().hex[:10]}_{filename}")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(file_path))

            file_size = file_path.stat().st_size if file_path.is_file() else 0
            if file_size <= 0:
                raise ValueError("下载文件为空")

            result = {
                "success": True,
                "filename": filename,
                "file_path": str(file_path),
                "file_size": file_size,
                "url": self._redact_url(download.url),
            }
            logger.info("导出下载成功（浏览器事件）: {}, 大小: {}字节", filename, file_size)
            return result
        except Exception as e:
            if file_responses:
                response = file_responses[-1]
                disposition = response.headers.get("content-disposition", "")
                filename_match = re.search(r"filename\\*?=(?:UTF-8''|[\"']?)([^;\"']+)", disposition, re.I)
                filename = self._safe_artifact_name(
                    unquote(filename_match.group(1)) if filename_match else f"export_{int(time.time())}.xlsx",
                    default=f"export_{int(time.time())}.xlsx",
                )
                file_path = self._runtime_artifact_path("downloads", f"{uuid.uuid4().hex[:10]}_{filename}")
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with file_path.open("wb") as export_file:
                    export_file.write(response.body())
                file_size = file_path.stat().st_size
                logger.info("从实时导出响应保存文件: {}, 大小: {}字节", filename, file_size)
                return {
                    "success": file_size > 0,
                    "filename": filename,
                    "file_path": str(file_path),
                    "file_size": file_size,
                    "url": self._redact_url(response.url),
                }
            if export_response_objects:
                response = export_response_objects[-1]
                try:
                    payload = response.json()
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    logger.info(
                        "实时导出接口结果: code={}, message={}, data_type={}",
                        payload.get("code"),
                        payload.get("message") or payload.get("msg"),
                        type(payload.get("data")).__name__,
                    )

                    def find_download_url(value):
                        if isinstance(value, str) and (
                            value.startswith(("http://", "https://", "/")) or ".xlsx" in value.lower()
                        ):
                            return value
                        if isinstance(value, dict):
                            preferred_keys = ("downloadUrl", "fileUrl", "url", "path")
                            for key in preferred_keys:
                                if key in value:
                                    found = find_download_url(value[key])
                                    if found:
                                        return found
                            for nested in value.values():
                                found = find_download_url(nested)
                                if found:
                                    return found
                        return None

                    download_url = find_download_url(payload.get("data"))
                    if download_url:
                        absolute_url = self._validate_same_origin_url(
                            urljoin(response.url, download_url), purpose="导出文件 URL"
                        )
                        api_response = self.page.context.request.get(absolute_url)
                        if api_response.ok:
                            disposition = api_response.headers.get("content-disposition", "")
                            filename_match = re.search(
                                r"filename\\*?=(?:UTF-8''|[\"']?)([^;\"']+)", disposition, re.I
                            )
                            filename = self._safe_artifact_name(
                                unquote(filename_match.group(1))
                                if filename_match
                                else os.path.basename(download_url.split("?", 1)[0])
                                or f"export_{int(time.time())}.xlsx",
                                default=f"export_{int(time.time())}.xlsx",
                            )
                            file_path = self._runtime_artifact_path("downloads", f"{uuid.uuid4().hex[:10]}_{filename}")
                            file_path.parent.mkdir(parents=True, exist_ok=True)
                            with file_path.open("wb") as export_file:
                                export_file.write(api_response.body())
                            file_size = file_path.stat().st_size
                            return {
                                "success": file_size > 0,
                                "filename": filename,
                                "file_path": str(file_path),
                                "file_size": file_size,
                                "url": self._redact_url(absolute_url),
                            }
            messages = self.page.locator(
                ".el-message:visible, .el-notification:visible, [role='alert']:visible"
            ).all_text_contents()
            logger.warning(
                "实时导出未产生文件，页面提示: {}，导出响应: {}",
                messages,
                export_responses[-10:],
            )
            return {
                "success": False,
                "error": self._redact_text(e),
                "filename": None,
                "file_path": None,
                "file_size": 0,
                "url": None,
            }
        finally:
            self.page.remove_listener("response", capture_file_response)

    @allure.step("下载到指定路径")
    def download_to(self, save_path: str, timeout: int = 120000) -> dict:
        target_path = self._resolve_download_path(save_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self.page.expect_download(timeout=timeout) as download_info:
                self.click_realtime_export()
                self.wait_for_page_settle(timeout=30000)

            download = download_info.value
            filename = self._safe_artifact_name(download.suggested_filename, default=target_path.name)
            download.save_as(str(target_path))

            file_size = target_path.stat().st_size if target_path.is_file() else 0
            if file_size <= 0:
                raise ValueError("下载文件为空")

            return {
                "success": True,
                "filename": filename,
                "file_path": str(target_path),
                "file_size": file_size,
                "url": self._redact_url(download.url),
            }
        except Exception as e:
            logger.warning(f"下载失败: {e}")

            try:
                import glob

                download_dir = target_path.parent
                base_name = target_path.stem

                max_wait = 60
                start_time = time.time()
                while time.time() - start_time < max_wait:
                    files = glob.glob(os.path.join(str(download_dir), f"*{base_name}*.xlsx"))
                    if files:
                        os.replace(files[0], target_path)
                        file_size = target_path.stat().st_size
                        if file_size <= 0:
                            raise ValueError("轮询到的下载文件为空")
                        return {
                            "success": True,
                            "filename": target_path.name,
                            "file_path": str(target_path),
                            "file_size": file_size,
                            "url": None,
                        }
                    self.wait_for_poll_interval(2000)

                logger.warning("轮询检测下载文件超时")
            except Exception as poll_e:
                logger.warning(f"轮询检测下载文件失败: {poll_e}")

            return {"success": False, "error": self._redact_text(e), "filename": None, "file_path": None, "file_size": 0, "url": None}

    @allure.step("获取导出页面标题")
    def get_page_title(self) -> str:
        title = self.page.title()
        return title if title else ""

    @allure.step("检查是否有导出结果")
    def has_export_results(self) -> bool:
        self.wait_for_page_settle(timeout=30000)
        no_data = self.page.locator('span:has-text("暂无数据"), div:has-text("暂无数据")')
        if no_data.count() > 0:
            logger.info("导出页面显示暂无数据")
            return False
        return True

    @allure.step("获取订单数量预览")
    def get_order_count_preview(self) -> int | None:
        try:
            count_element = self.page.locator('div:has-text("条)")').first
            if count_element.count() > 0:
                text = count_element.text_content() or ""
                import re

                match = re.search(r"(\d+)\s*条", text)
                if match:
                    return int(match.group(1))
            return None
        except Exception as e:
            logger.warning(f"获取订单数量预览失败: {e}")
            return None

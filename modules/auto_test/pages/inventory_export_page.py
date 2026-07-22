import os
import time

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
                    logger.info(f"当前页面已跳转到导出页面: {self.page.url}")
                    return True

                pages = self.page.context.pages
                for pg in pages:
                    if "exportPage" in pg.url:
                        self.page = pg
                        logger.info(f"已切换到导出页面: {pg.url}")
                        return True

                time.sleep(1)

            logger.warning(f"未找到导出页面，当前页面URL: {self.page.url}")
            return False
        except Exception as e:
            logger.warning(f"等待导出页面超时: {e}")
            return False

    @allure.step("检查是否在导出页面")
    def is_on_export_page(self) -> bool:
        return "exportPage" in self.page.url

    @allure.step("获取当前URL")
    def get_current_url(self) -> str:
        return self.page.url

    @allure.step("全选导出字段")
    def select_all_fields(self) -> None:
        self.page.wait_for_timeout(500)

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

            for i in range(min(30, checkbox_count)):
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
            checked = self.page.locator('input[type="checkbox"]:checked').all()
            for cb in checked:
                cb.click(force=True)
            logger.info("已清空所有字段")
        except Exception as e:
            logger.warning(f"清空字段失败: {e}")

    @allure.step("选择指定字段: {field_name}")
    def select_field(self, field_name: str) -> bool:
        try:
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

    @allure.step("获取总字段数量")
    def get_total_field_count(self) -> int:
        try:
            count = self.page.locator('input[type="checkbox"]').count()
            return count
        except Exception:
            return 0

    @allure.step("点击实时导出按钮")
    def click_realtime_export(self) -> None:
        self.page.wait_for_timeout(1000)
        export_btns = self.page.locator('button:has-text("实时导出")').all()
        if export_btns:
            export_btns[0].click()
            logger.info("点击实时导出按钮")
        else:
            logger.warning("未找到实时导出按钮")
            self.page.wait_for_timeout(1000)
            export_btns = self.page.locator('button:has-text("实时导出")').all()
            if export_btns:
                export_btns[0].click()
                logger.info("点击实时导出按钮")

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
        try:
            with self.page.expect_download(timeout=timeout) as download_info:
                self.click_realtime_export()

            download = download_info.value
            filename = download.suggested_filename
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
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
            logger.warning(f"下载失败: {e}")
            return {"success": False, "error": str(e), "filename": None, "file_path": None, "file_size": 0, "url": None}

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

import allure
import uuid
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class ExportPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self.export_url_pattern = "product/productCenter/exportPage"

    @allure.step("等待导出页面加载")
    def wait_for_export_page(self, timeout: int = 30000) -> bool:
        try:
            self.page.wait_for_url(f"**/{self.export_url_pattern}", timeout=timeout)
            self.wait_for_load_state()
            logger.info("导出页面加载完成")
            return True
        except Exception as e:
            logger.warning(f"等待导出页面超时: {e}")
            return False

    @allure.step("点击实时导出按钮")
    def click_real_time_export(self) -> bool:
        real_time_btn = self.page.locator('button:has-text("实时导出")')
        if real_time_btn.count() > 0:
            real_time_btn.first.click()
            logger.info("点击实时导出按钮")
            return True
        else:
            logger.warning("未找到实时导出按钮")
            self.wait_for_loading_complete(timeout=10000)
            real_time_btn = self.page.locator('button:has-text("实时导出")')
            if real_time_btn.count() > 0:
                real_time_btn.first.click()
                logger.info("点击实时导出按钮")
                return True
            logger.warning("未找到可用的实时导出按钮")
            return False

    @allure.step("等待下载完成")
    def wait_for_download(self, timeout: int = 60000) -> dict:
        try:
            with self.page.expect_download(timeout=timeout) as download_info:
                if not self.click_real_time_export():
                    raise ValueError("未找到可用的实时导出按钮")

            download = download_info.value
            filename = self._safe_artifact_name(
                download.suggested_filename,
                default=f"export_{uuid.uuid4().hex[:10]}.xlsx",
            )
            download_path = self._runtime_artifact_path(
                "downloads", f"{uuid.uuid4().hex[:10]}_{filename}"
            )
            download_path.parent.mkdir(parents=True, exist_ok=True)
            download.save_as(str(download_path))
            file_size = download_path.stat().st_size if download_path.is_file() else 0
            if file_size <= 0:
                raise ValueError("下载文件为空")

            result = {
                "success": True,
                "filename": filename,
                "path": str(download_path),
                "size": file_size,
                "url": self._redact_url(download.url),
            }
            logger.info(f"导出下载成功: {filename}, 大小: {file_size}字节")
            return result
        except Exception as e:
            logger.warning(f"导出下载超时或失败: {e}")
            return {"success": False, "error": self._redact_text(e)}

    @allure.step("获取当前页面URL")
    def get_current_url(self) -> str:
        return self.page.url

    @allure.step("验证导出页面URL包含sku参数")
    def verify_url_has_sku_param(self) -> bool:
        url = self.get_current_url()
        return "sku" in url.lower()

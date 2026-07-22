from typing import Any

from playwright.sync_api import BrowserContext, Page

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger
from modules.auto_test.drivers.browser_driver import BrowserDriver

logger = get_logger()


class PlaywrightManager:
    """Backward-compatible wrapper around BrowserDriver (single context per start/stop)."""

    def __init__(self) -> None:
        self.config = get_config()
        self._driver = BrowserDriver()
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def start(self, **kwargs: Any) -> Page:
        browser_name = kwargs.get("browser", self.config.get("playwright.browser", "chromium"))
        headless = kwargs.get("headless", self.config.get("playwright.headless", True))
        slow_mo = kwargs.get("slow_mo", self.config.get("playwright.slow_mo", 0))

        self._driver.start_browser(browser=browser_name, headless=headless, slow_mo=slow_mo)
        self.context, self.page = self._driver.new_context_and_page()
        logger.info("Browser started: %s, headless=%s", browser_name, headless)
        return self.page

    def stop(self, trace_path: str | None = None) -> None:
        if self.context is not None:
            self._driver.close_context(self.context, trace_path=trace_path)
            self.context = None
            self.page = None
        self._driver.shutdown_browser()
        logger.info("Browser stopped")

    def take_screenshot(self, path: str) -> None:
        if self.page:
            self.page.screenshot(path=path, full_page=True)
            logger.info("Screenshot saved: %s", path)

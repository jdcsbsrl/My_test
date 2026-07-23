"""Playwright transport: browser launch, context, page. No pytest / Allure."""

from __future__ import annotations

import os
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger

logger = get_logger()


class BrowserDriver:
    """Manages Playwright lifecycle: one Browser, many contexts (test isolation)."""

    def __init__(self) -> None:
        self.config = get_config()
        self._playwright: Any = None
        self.browser: Browser | None = None

    def start_browser(self, *, browser: str, headless: bool, slow_mo: int) -> Browser:
        if self.browser is not None:
            return self.browser

        self._playwright = sync_playwright().start()
        cdp_url = (os.getenv("PLAYWRIGHT_CDP_ENDPOINT") or "").strip()
        if cdp_url:
            if browser != "chromium":
                logger.warning("BrowserDriver: CDP connect forces chromium semantics; requested=%s", browser)
            self.browser = self._playwright.chromium.connect_over_cdp(cdp_url)
            logger.info("BrowserDriver: connected over CDP")
            return self.browser

        browser_type = getattr(self._playwright, browser)
        launch_options: dict[str, Any] = {"headless": headless, "slow_mo": slow_mo}
        browser_channel = (os.getenv("PLAYWRIGHT_BROWSER_CHANNEL") or "").strip()
        if browser_channel:
            if browser != "chromium":
                raise ValueError("PLAYWRIGHT_BROWSER_CHANNEL 仅支持 chromium")
            launch_options["channel"] = browser_channel
        self.browser = browser_type.launch(**launch_options)
        logger.info(f"BrowserDriver: started {browser}, headless={headless}")
        return self.browser

    def new_context_and_page(self) -> tuple[BrowserContext, Page]:
        if self.browser is None:
            raise RuntimeError("BrowserDriver.start_browser must be called before new_context_and_page")

        viewport = self.config.get("playwright.viewport", {"width": 1920, "height": 1080})
        context_options: dict[str, Any] = {
            "viewport": viewport,
            "accept_downloads": True,
            "record_video_dir": None,
            "record_video_size": None,
        }

        video_config = self.config.get("playwright.video", "off")
        if video_config in ("on", "retain-on-failure"):
            context_options["record_video_dir"] = "reports/videos"
            context_options["record_video_size"] = viewport

        context = self.browser.new_context(**context_options)

        trace_config = self.config.get("playwright.trace", "off")
        if trace_config in ("on", "retain-on-failure", "on-first-retry"):
            context.tracing.start(screenshots=True, snapshots=True, sources=True)

        page = context.new_page()
        return context, page

    def close_context(self, context: BrowserContext, *, trace_path: str | None = None) -> None:
        trace_config = self.config.get("playwright.trace", "off")
        if trace_config != "off" and trace_path:
            context.tracing.stop(path=trace_path)
        context.close()

    def shutdown_browser(self) -> None:
        if self.browser:
            self.browser.close()
            self.browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
        logger.info("BrowserDriver: shutdown complete")

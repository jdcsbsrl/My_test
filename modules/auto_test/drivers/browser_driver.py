"""Playwright transport: browser launch, context, page. No pytest / Allure."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger
from modules.trae_test.utils.runtime_paths import runtime_dir

logger = get_logger()


def _safe_runtime_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return cleaned or "unknown"


def _runtime_video_dir(run_id: str | None = None, worker_id: str | None = None) -> Path:
    run_id = _safe_runtime_component(
        run_id or os.getenv("TEST_RUN_ID") or os.getenv("PYTEST_XDIST_TESTRUNUID", "local")
    )
    worker_id = _safe_runtime_component(worker_id or os.getenv("PYTEST_XDIST_WORKER", "master"))
    target = runtime_dir("reports") / "runs" / run_id / worker_id / "videos"
    target.mkdir(parents=True, exist_ok=True)
    return target


class BrowserDriver:
    """Manages Playwright lifecycle: one Browser, many contexts (test isolation)."""

    def __init__(self, *, run_id: str | None = None, worker_id: str | None = None) -> None:
        self.config = get_config()
        self._playwright: Any = None
        self.browser: Browser | None = None
        self._contexts: list[BrowserContext] = []
        self._tracing_contexts: list[BrowserContext] = []
        self._run_id = run_id
        self._worker_id = worker_id

    def start_browser(self, *, browser: str, headless: bool, slow_mo: int) -> Browser:
        if self.browser is not None:
            return self.browser

        # Prefer the repository-managed browser bundle so local runs and CI
        # use the same executable. An explicit environment override still wins.
        repo_browsers = Path(__file__).resolve().parents[3] / "browsers"
        configured_browsers = (
            Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"]) if os.getenv("PLAYWRIGHT_BROWSERS_PATH") else None
        )
        if repo_browsers.is_dir() and (configured_browsers is None or not configured_browsers.is_dir()):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(repo_browsers)
            logger.info("BrowserDriver: using repository browsers at %s", repo_browsers)

        self._playwright = sync_playwright().start()
        try:
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
        except Exception:
            playwright = self._playwright
            self.browser = None
            self._playwright = None
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    logger.exception("BrowserDriver: failed to stop Playwright after startup failure")
            raise

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
            context_options["record_video_dir"] = str(_runtime_video_dir(self._run_id, self._worker_id))
            context_options["record_video_size"] = viewport

        context = self.browser.new_context(**context_options)
        self._contexts.append(context)
        trace_started = False
        try:
            trace_config = self.config.get("playwright.trace", "off")
            if trace_config in ("on", "retain-on-failure", "on-first-retry"):
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                trace_started = True
                self._tracing_contexts.append(context)

            page = context.new_page()
            return context, page
        except Exception:
            if trace_started:
                try:
                    context.tracing.stop()
                except Exception:
                    logger.exception("BrowserDriver: failed to stop trace after context creation failure")
            try:
                context.close()
            except Exception:
                logger.exception("BrowserDriver: failed to close context after page creation failure")
            self._discard_context(context)
            self._discard_context(context, tracing=True)
            raise

    def close_context(
        self,
        context: BrowserContext,
        *,
        page: Page | None = None,
        trace_path: str | None = None,
    ) -> None:
        """Close page, trace, and context in that order, retaining all errors."""
        errors: list[Exception] = []

        if page is not None:
            try:
                page.close()
            except Exception as exc:
                errors.append(exc)
                logger.exception("BrowserDriver: failed to close page")

        if trace_path is not None or self._contains_context(self._tracing_contexts, context):
            try:
                if trace_path is not None:
                    self._validate_trace_path(trace_path)
                    context.tracing.stop(path=trace_path)
                else:
                    context.tracing.stop()
            except Exception as exc:
                errors.append(exc)
                logger.exception("BrowserDriver: failed to save trace")
            finally:
                self._discard_context(context, tracing=True)
        try:
            context.close()
        except Exception as exc:
            errors.append(exc)
            logger.exception("BrowserDriver: failed to close browser context")
        finally:
            self._discard_context(context)
        if errors:
            raise RuntimeError("Browser context teardown failed") from errors[0]

    @staticmethod
    def _validate_trace_path(trace_path: str) -> None:
        reports_root = runtime_dir("reports", create=False).resolve()
        candidate = Path(trace_path)
        if not candidate.is_absolute() and candidate.parts[:1] == (".runtime",):
            candidate = reports_root.parent.parent / candidate
        resolved = candidate.resolve()
        if resolved != reports_root and reports_root not in resolved.parents:
            raise ValueError(f"Trace path must remain under .runtime/reports: {trace_path}")

    def shutdown_browser(self) -> None:
        errors: list[Exception] = []
        browser = self.browser
        playwright = self._playwright
        self.browser = None
        self._playwright = None

        for context in list(reversed(self._contexts)):
            try:
                self.close_context(context)
            except Exception as exc:
                errors.append(exc)

        if browser:
            try:
                browser.close()
            except Exception as exc:
                errors.append(exc)
                logger.exception("BrowserDriver: failed to close browser")
        if playwright:
            try:
                playwright.stop()
            except Exception as exc:
                errors.append(exc)
                logger.exception("BrowserDriver: failed to stop Playwright")
        self._contexts.clear()
        self._tracing_contexts.clear()
        logger.info("BrowserDriver: shutdown complete")
        if errors:
            raise RuntimeError("Browser teardown failed") from errors[0]

    @staticmethod
    def _contains_context(contexts: list[BrowserContext], target: BrowserContext) -> bool:
        return any(candidate is target for candidate in contexts)

    def _discard_context(self, context: BrowserContext, *, tracing: bool = False) -> None:
        target = self._tracing_contexts if tracing else self._contexts
        target[:] = [candidate for candidate in target if candidate is not context]

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import allure
from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeoutError, expect

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger, redact_sensitive_data
from modules.auto_test.core.self_healing import LocatorContext, SelfHealingLocator
from modules.trae_test.utils.runtime_paths import project_root, runtime_dir

logger = get_logger()


class BasePage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.config = get_config()
        self.base_url = self.config.base_url
        self.self_healing = SelfHealingLocator(page, env=getattr(self.config, "env", "test"))

    @staticmethod
    def _safe_runtime_component(value: str, default: str = "unknown") -> str:
        cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "")).strip("._")
        return cleaned[:100] or default

    @classmethod
    def _safe_artifact_name(cls, value: str, *, default: str = "artifact", suffix: str = "") -> str:
        """Return a filename that cannot escape its runtime artifact directory."""
        raw = str(value or "").replace("\\", "/")
        name = raw.rsplit("/", 1)[-1].replace("\x00", "")
        name = re.sub(r"[<>:\"|?*\r\n\t]+", "_", name).strip(" .")
        if name in {"", ".", ".."}:
            name = default
        if suffix and not name.lower().endswith(suffix.lower()):
            name = f"{name}{suffix}"
        return name[:180]

    @classmethod
    def _runtime_scope(cls, kind: str) -> Path:
        run_id = cls._safe_runtime_component(os.getenv("TEST_RUN_ID", "local"), "local")
        worker_id = cls._safe_runtime_component(os.getenv("PYTEST_XDIST_WORKER", "master"), "master")
        target = runtime_dir(kind) / "runs" / run_id / worker_id
        target.mkdir(parents=True, exist_ok=True)
        return target

    @classmethod
    def _runtime_artifact_path(cls, kind: str, filename: str) -> Path:
        return cls._runtime_scope(kind) / cls._safe_artifact_name(filename)

    @classmethod
    def _resolve_download_path(cls, save_path: str) -> Path:
        """Resolve a caller-supplied download path strictly below runtime downloads."""
        raw = str(save_path or "").strip()
        if not raw:
            raise ValueError("下载路径不能为空")
        normalized = raw.replace("\\", "/")
        if normalized.startswith(".runtime/downloads/") or normalized == ".runtime/downloads":
            candidate = project_root() / normalized
        elif Path(raw).is_absolute():
            candidate = Path(raw)
        else:
            # Legacy callers pass ``downloads/...`` or a bare filename. Keep the
            # API compatible while moving the actual output into .runtime.
            relative = normalized.removeprefix("downloads/")
            candidate = runtime_dir("downloads") / relative

        downloads_root = runtime_dir("downloads").resolve()
        resolved = candidate.resolve()
        if resolved != downloads_root and downloads_root not in resolved.parents:
            raise ValueError(f"下载路径必须位于 .runtime/downloads 内: {save_path!r}")
        if resolved.name in {"", ".", ".."}:
            raise ValueError(f"下载文件名无效: {save_path!r}")
        return resolved

    def _validate_same_origin_url(self, value: str, *, purpose: str = "URL") -> str:
        parsed = urlsplit(str(value or "").strip())
        base = urlsplit(str(self.base_url or "").strip())
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.fragment
            or "\\" in parsed.path
            or ".." in parsed.path.split("/")
        ):
            raise ValueError(f"{purpose} 格式不安全")
        if (parsed.scheme.lower(), parsed.netloc.lower()) != (base.scheme.lower(), base.netloc.lower()):
            raise ValueError(f"{purpose} 必须与当前测试环境同源")
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))

    @staticmethod
    def _redact_url(value: str) -> str:
        parsed = urlsplit(str(value or ""))
        if not parsed.scheme or not parsed.netloc:
            return "[REDACTED URL]" if "?" in str(value) else str(value)
        safe_netloc = parsed.hostname or parsed.netloc
        if parsed.port:
            safe_netloc = f"{safe_netloc}:{parsed.port}"
        query = "[REDACTED]" if parsed.query else ""
        return urlunsplit((parsed.scheme, safe_netloc, parsed.path, query, ""))

    @staticmethod
    def _redact_text(value: object) -> str:
        return str(redact_sensitive_data(str(value or "")))

    @allure.step("Navigate to URL")
    def navigate_to(self, url: str) -> None:
        raw_url = str(url or "").strip()
        parsed = urlsplit(raw_url)
        if raw_url.startswith("//"):
            raise ValueError("不允许使用协议相对 URL")
        if parsed.scheme or parsed.netloc:
            url = self._validate_same_origin_url(raw_url, purpose="导航 URL")
        else:
            if not self.base_url:
                raise ValueError("base_url 为空，请检查环境变量 TEST_WEB_BASE_URL 或 TEST_WEB_API_BASE_URL 是否已设置")
            if any(char in raw_url for char in ("\r", "\n", "\\")) or ".." in parsed.path.split("/"):
                raise ValueError("导航路径不安全")
            if parsed.fragment:
                raise ValueError("导航 URL 不允许 fragment")
            base_url = self.base_url.rstrip("/")
            if url and base_url.endswith("/index"):
                base_url = base_url[: -len("/index")]
            url = f"{base_url}/{raw_url.lstrip('/')}" if raw_url else f"{base_url}/"
            url = self._validate_same_origin_url(url, purpose="导航 URL")
        self.page.goto(url)
        logger.info("Navigated to: {}", self._redact_url(url))

    def wait_for_business_ready(
        self,
        selectors: list[str],
        *,
        page_name: str,
        initial_timeout: int = 30000,
        retry_timeout: int = 45000,
        max_route_retries: int = 1,
    ) -> None:
        """Wait for a route's business controls with bounded route retries.

        DOMContentLoaded only proves that the application shell arrived. SPA
        routes can still be waiting for their component bundle or data request,
        so callers must provide controls that are unique to the business page.
        Retries are deliberately bounded and only repeat the route bootstrap;
        they never turn a final timeout into a passing test.
        """
        selector = ", ".join(item.strip() for item in selectors if item.strip())
        if not selector:
            raise ValueError(f"{page_name} business-ready selectors cannot be empty")
        if max_route_retries < 0:
            raise ValueError("max_route_retries cannot be negative")
        ready_locator = self.page.locator(selector).first
        self.wait_for_load_state("domcontentloaded")
        try:
            ready_locator.wait_for(state="visible", timeout=initial_timeout)
        except PlaywrightTimeoutError:
            logger.warning(
                "{} business controls not ready after {}s; retrying route: url={}, title={}",
                page_name,
                initial_timeout // 1000,
                self._redact_url(self.page.url),
                self._redact_text(self.page.title()),
            )
            try:
                self.take_screenshot(f"{page_name}_bootstrap_timeout")
            except Exception as screenshot_error:
                logger.debug("Unable to capture {} bootstrap screenshot: {}", page_name, screenshot_error)
            last_error: Exception | None = None
            for retry_index in range(1, max_route_retries + 1):
                try:
                    self.page.reload(wait_until="domcontentloaded", timeout=60000)
                    ready_locator.wait_for(state="visible", timeout=retry_timeout)
                    logger.info(
                        "{} business controls became ready after route retry {}/{}",
                        page_name,
                        retry_index,
                        max_route_retries,
                    )
                    return
                except Exception as retry_error:
                    last_error = retry_error
                    if retry_index < max_route_retries:
                        logger.warning(
                            "{} business controls still unavailable after route retry {}/{}; "
                            "retrying once more: url={}, title={}",
                            page_name,
                            retry_index,
                            max_route_retries,
                            self._redact_url(self.page.url),
                            self._redact_text(self.page.title()),
                        )
            raise PlaywrightTimeoutError(
                f"{page_name} business controls were not ready after initial wait and "
                f"{max_route_retries} route retries"
            ) from last_error
        logger.info("{} business controls are ready", page_name)

    @allure.step("Click element: {selector}")
    def click(self, selector: str) -> None:
        try:
            self.page.locator(selector).click()
            logger.info(f"Clicked: {selector}")
        except Exception:
            if not self.self_healing.enabled:
                raise
            context = LocatorContext(selector=selector, selectors=[selector], description=selector)
            if not self.self_healing.execute("click", context, lambda locator: locator.click()):
                raise
            logger.info(f"Self-healed click: {selector}")

    def fill(self, selector: str, value: str) -> None:
        # Allure records function arguments for decorated steps. Never record
        # the value passed to an input because it may be a password or token.
        with allure.step(f"Fill input {selector}"):
            try:
                self.page.locator(selector).fill(value)
                logger.info(f"Filled {selector}")
                return
            except Exception:
                if not self.self_healing.enabled:
                    raise
                context = LocatorContext(selector=selector, selectors=[selector], description=selector)
                if not self.self_healing.execute("fill", context, lambda locator: locator.fill(value)):
                    raise
                logger.info(f"Self-healed fill: {selector}")

    def type_text(self, selector: str, value: str, delay: int = 0) -> None:
        with allure.step(f"Type text into {selector}"):
            self.page.locator(selector).press_sequentially(value, delay=delay)
            logger.info(f"Typed into {selector}")

    def select_option(self, selector: str, value: str) -> None:
        with allure.step(f"Select option from {selector}"):  # nosec B608
            self.page.locator(selector).select_option(value)
            logger.info("Selected option")

    @allure.step("Get element: {selector}")
    def get_element(self, selector: str) -> Locator:
        return self.page.locator(selector)

    @allure.step("Get element by role: {role}")
    def get_by_role(self, role: str, name: str | None = None) -> Locator:
        return self.page.get_by_role(role, name=name)

    @allure.step("Get element by text")
    def get_by_text(self, text: str) -> Locator:
        return self.page.get_by_text(text)

    @allure.step("Get element by test id: {test_id}")
    def get_by_test_id(self, test_id: str) -> Locator:
        return self.page.get_by_test_id(test_id)

    @allure.step("Wait for element: {selector}")
    def wait_for_element(self, selector: str, timeout: int = 10000) -> None:
        try:
            self.page.locator(selector).wait_for(timeout=timeout)
        except Exception:
            if not self.self_healing.enabled:
                raise

    @allure.step("等待页面加载完成")
    def wait_for_loading_complete(self, selectors: list[str] | None = None, timeout: int = 30000) -> None:
        """Wait for common loading indicators to disappear instead of sleeping."""
        loading_selectors = selectors or [
            ".el-loading-mask",
            ".el-loading-spinner",
            "[aria-busy='true']",
            "[data-loading='true']",
        ]
        for loading_selector in loading_selectors:
            locator = self.page.locator(loading_selector)
            if locator.count():
                locator.first.wait_for(state="hidden", timeout=timeout)

    @allure.step("等待页面稳定")
    def wait_for_page_settle(self, timeout: int = 30000) -> None:
        """Wait for navigation and common loading indicators to settle."""
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            logger.debug("DOM content load did not settle within timeout")
        self.wait_for_loading_complete(timeout=timeout)

    def wait_for_poll_interval(self, milliseconds: int = 250) -> None:
        """Yield between bounded polling attempts; use only inside polling loops."""
        self.page.wait_for_timeout(milliseconds)

    @allure.step("等待业务元素可操作")
    def wait_for_actionable(self, selector: str, timeout: int = 30000) -> Locator:
        """Return a visible and enabled element for a deterministic action."""
        locator = self.page.locator(selector).first
        locator.wait_for(state="visible", timeout=timeout)
        expect(locator).to_be_enabled(timeout=timeout)
        return locator

    @allure.step("Wait for page load")
    def wait_for_load_state(self, state: str = "domcontentloaded") -> None:
        self.page.wait_for_load_state(state)

    @allure.step("Assert element visible: {selector}")
    def assert_visible(self, selector: str) -> None:
        expect(self.page.locator(selector)).to_be_visible()

    @allure.step("Assert element contains expected text")
    def assert_contains_text(self, selector: str, text: str) -> None:
        expect(self.page.locator(selector)).to_contain_text(text)

    @allure.step("Assert page title contains expected text")
    def assert_title_contains(self, title: str) -> None:
        expect(self.page).to_have_title(title)

    @allure.step("Assert URL matches expected pattern")
    def assert_url_contains(self, url: str) -> None:
        expect(self.page).to_have_url(url)

    @allure.step("Take screenshot")
    def take_screenshot(self, name: str) -> None:
        safe_name = self._safe_artifact_name(name, default="screenshot", suffix=".png")
        screenshot_name = f"{safe_name.rsplit('.', 1)[0]}_{uuid.uuid4().hex[:10]}.png"
        path = self._runtime_scope("reports") / "screenshots" / screenshot_name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.page.screenshot(path=str(path), full_page=True)
        allure.attach.file(str(path), name=safe_name, attachment_type=allure.attachment_type.PNG)
        logger.info("Screenshot saved: {}", path)

    @allure.step("Get element text: {selector}")
    def get_text(self, selector: str) -> str:
        return self.page.locator(selector).text_content() or ""

    @allure.step("Get element attribute: {attribute} from {selector}")
    def get_attribute(self, selector: str, attribute: str) -> str | None:
        return self.page.locator(selector).get_attribute(attribute)

    @allure.step("Scroll to element: {selector}")
    def scroll_to(self, selector: str) -> None:
        self.page.locator(selector).scroll_into_view_if_needed()

    @allure.step("Hover over element: {selector}")
    def hover(self, selector: str) -> None:
        self.page.locator(selector).hover()

    @property
    def current_url(self) -> str:
        return self.page.url

    @property
    def title(self) -> str:
        return self.page.title()

    @allure.step("Try click with multiple selectors")
    def try_click(self, selectors: list[str], timeout: int = 10000) -> bool:
        """尝试多个选择器进行点击，直到成功

        Args:
            selectors: 选择器列表
            timeout: 超时时间（毫秒）

        Returns:
            是否成功点击
        """
        context = LocatorContext(selector=selectors[0] if selectors else None, selectors=selectors)
        if (
            len(selectors) > 1
            and self.self_healing.enabled
            and self.self_healing.execute("try_click", context, lambda locator: locator.click(), timeout=timeout)
        ):
            return True

        for selector in selectors:
            try:
                self.wait_for_element(selector, timeout)
                self.click(selector)
                logger.info(f"成功点击: {selector}")
                return True
            except Exception as e:
                logger.debug(f"尝试选择器 {selector} 失败: {e}")
                continue
        logger.warning(f"无法找到任何选择器: {selectors}")
        return False

    def try_fill(self, selectors: list[str], value: str, timeout: int = 10000) -> bool:
        """尝试多个选择器进行填充，直到成功

        Args:
            selectors: 选择器列表
            value: 填充值
            timeout: 超时时间（毫秒）

        Returns:
            是否成功填充
        """
        with allure.step("Try fill with multiple selectors"):
            context = LocatorContext(selector=selectors[0] if selectors else None, selectors=selectors)
            if (
                len(selectors) > 1
                and self.self_healing.enabled
                and self.self_healing.execute("try_fill", context, lambda locator: locator.fill(value), timeout=timeout)
            ):
                return True

            for selector in selectors:
                try:
                    self.wait_for_element(selector, timeout)
                    self.fill(selector, value)
                    logger.info(f"成功填充 {selector}")
                    return True
                except Exception as e:
                    logger.debug(f"尝试选择器 {selector} 失败: {e}")
                    continue
            logger.warning(f"无法找到任何选择器进行填充: {selectors}")
            return False

    @allure.step("Try click by role with variants")
    def try_click_by_role(self, role: str, name_variants: list[str], timeout: int = 10000) -> bool:
        """尝试多个名称变体通过role进行点击

        Args:
            role: 角色类型
            name_variants: 名称变体列表
            timeout: 超时时间（毫秒）

        Returns:
            是否成功点击
        """
        context = LocatorContext(
            role=role,
            names=name_variants,
            description=name_variants[0] if name_variants else role,
        )
        if (
            len(name_variants) > 1
            and self.self_healing.enabled
            and self.self_healing.execute(
                "try_click_by_role", context, lambda locator: locator.click(), timeout=timeout
            )
        ):
            return True

        for name in name_variants:
            try:
                element = self.get_by_role(role, name=name)
                element.wait_for(timeout=timeout)
                element.click()
                logger.info(f"成功通过role点击: {role}={name}")
                return True
            except Exception as e:
                logger.debug(f"尝试role {role}={name} 失败: {e}")
                continue
        logger.warning(f"无法找到任何role匹配: {role}")
        return False

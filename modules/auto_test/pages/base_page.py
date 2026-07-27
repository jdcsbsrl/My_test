import allure
from playwright.sync_api import Locator, Page, expect

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger
from modules.auto_test.core.self_healing import LocatorContext, SelfHealingLocator

logger = get_logger()


class BasePage:
    def __init__(self, page: Page) -> None:
        self.page = page
        self.config = get_config()
        self.base_url = self.config.base_url
        self.self_healing = SelfHealingLocator(page, env=getattr(self.config, "env", "test"))

    @allure.step("Navigate to {url}")
    def navigate_to(self, url: str) -> None:
        if not url.startswith("http"):
            if not self.base_url:
                raise ValueError("base_url 为空，请检查环境变量 TEST_WEB_BASE_URL 或 TEST_WEB_API_BASE_URL 是否已设置")
            base_url = self.base_url.rstrip("/")
            if url and base_url.endswith("/index"):
                base_url = base_url[: -len("/index")]
            url = f"{base_url}/{url.lstrip('/')}" if url else f"{base_url}/"
        self.page.goto(url)
        logger.info(f"Navigated to: {url}")

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

    @allure.step("Fill input {selector} with value")
    def fill(self, selector: str, value: str) -> None:
        try:
            self.page.locator(selector).fill(value)
            logger.info(f"Filled {selector}")
        except Exception:
            if not self.self_healing.enabled:
                raise
            context = LocatorContext(selector=selector, selectors=[selector], description=selector)
            if not self.self_healing.execute("fill", context, lambda locator: locator.fill(value)):
                raise
            logger.info(f"Self-healed fill: {selector}")

    @allure.step("Type text into {selector}")
    def type_text(self, selector: str, value: str, delay: int = 0) -> None:
        self.page.locator(selector).press_sequentially(value, delay=delay)
        logger.info(f"Typed into {selector}")

    @allure.step("Select option {value} from {selector}")
    def select_option(self, selector: str, value: str) -> None:
        self.page.locator(selector).select_option(value)
        logger.info(f"Selected {value} from {selector}")

    @allure.step("Get element: {selector}")
    def get_element(self, selector: str) -> Locator:
        return self.page.locator(selector)

    @allure.step("Get element by role: {role}")
    def get_by_role(self, role: str, name: str | None = None) -> Locator:
        return self.page.get_by_role(role, name=name)

    @allure.step("Get element by text: {text}")
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
            context = LocatorContext(selector=selector, selectors=[selector], description=selector)
            if not self.self_healing.execute(
                "wait_for_element", context, lambda locator: locator.wait_for(timeout=timeout)
            ):
                raise

    @allure.step("Wait for page load")
    def wait_for_load_state(self, state: str = "domcontentloaded") -> None:
        self.page.wait_for_load_state(state)

    @allure.step("Assert element visible: {selector}")
    def assert_visible(self, selector: str) -> None:
        expect(self.page.locator(selector)).to_be_visible()

    @allure.step("Assert element contains text: {text}")
    def assert_contains_text(self, selector: str, text: str) -> None:
        expect(self.page.locator(selector)).to_contain_text(text)

    @allure.step("Assert page title contains: {title}")
    def assert_title_contains(self, title: str) -> None:
        expect(self.page).to_have_title(title)

    @allure.step("Assert URL contains: {url}")
    def assert_url_contains(self, url: str) -> None:
        expect(self.page).to_have_url(url)

    @allure.step("Take screenshot: {name}")
    def take_screenshot(self, name: str) -> None:
        path = f"reports/screenshots/{name}.png"
        self.page.screenshot(path=path, full_page=True)
        allure.attach.file(path, name=name, attachment_type=allure.attachment_type.PNG)
        logger.info(f"Screenshot: {path}")

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
        if len(selectors) > 1 and self.self_healing.enabled and self.self_healing.execute(
            "try_click", context, lambda locator: locator.click(), timeout=timeout
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

    @allure.step("Try fill with multiple selectors")
    def try_fill(self, selectors: list[str], value: str, timeout: int = 10000) -> bool:
        """尝试多个选择器进行填充，直到成功

        Args:
            selectors: 选择器列表
            value: 填充值
            timeout: 超时时间（毫秒）

        Returns:
            是否成功填充
        """
        context = LocatorContext(selector=selectors[0] if selectors else None, selectors=selectors)
        if len(selectors) > 1 and self.self_healing.enabled and self.self_healing.execute(
            "try_fill", context, lambda locator: locator.fill(value), timeout=timeout
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
        if len(name_variants) > 1 and self.self_healing.enabled and self.self_healing.execute(
            "try_click_by_role", context, lambda locator: locator.click(), timeout=timeout
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

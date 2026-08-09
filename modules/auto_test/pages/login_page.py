import allure
from playwright.sync_api import Page

from modules.auto_test.core.logger import get_logger
from modules.auto_test.pages.base_page import BasePage

logger = get_logger()


class LoginPage(BasePage):
    def __init__(self, page: Page) -> None:
        super().__init__(page)
        self._username_selectors = [
            'input[placeholder="账号"]',
            '.el-input__inner[type="text"]',
            'input[type="text"].el-input__inner',
            'input[type="text"]',
            'input[placeholder*="账号"]',
            'input[placeholder*="用户名"]',
            'input[name="username"]',
            'input[id*="username"]',
        ]
        self._password_selectors = [
            'input[placeholder="密码"]',
            '.el-input__inner[type="password"]',
            'input[type="password"].el-input__inner',
            'input[type="password"]',
            'input[placeholder*="密码"]',
            'input[name="password"]',
            'input[id*="password"]',
        ]
        self._login_button_selectors = [
            'button:has-text("登 录")',
            ".el-button--primary",
            ".el-button.el-button--primary",
            "button.el-button--primary",
            '//button[contains(text(), "登")]',
            '//button[contains(text(), "录")]',
            'button[type="button"].el-button--primary',
            'button[type="button"]',
            'button:has-text("登录")',
            '//button[contains(text(), "登录")]',
            'button[type="submit"]',
            'input[type="submit"]',
            ".ant-btn-primary",
            ".login-btn",
            ".login-button",
            '[data-testid="login-btn"]',
            '[data-test-id="login-btn"]',
            "#login-btn",
            "#submit-btn",
            "form button",
            "form > button",
            ".btn-primary",
            ".submit-btn",
            "button.submit",
            "button.primary",
        ]

    @allure.step("Navigate to login page")
    def navigate_to_login(self) -> None:
        """导航到登录页面（通过SPA入口，让前端自动跳转登录页）"""
        self.navigate_to("")
        logger.info("导航到登录页面")

    @allure.step("Enter username: {username}")
    def enter_username(self, username: str) -> None:
        """输入用户名"""
        if not self.try_fill(self._username_selectors, username):
            raise ValueError("无法找到用户名输入框")
        logger.info(f"输入用户名: {username}")

    @allure.step("Enter password")
    def enter_password(self, password: str) -> None:
        """输入密码"""
        if not self.try_fill(self._password_selectors, password):
            raise ValueError("无法找到密码输入框")
        logger.info("输入密码")

    @allure.step("Click login button")
    def click_login(self) -> None:
        """点击登录按钮"""
        if self.try_click(self._login_button_selectors):
            logger.info("点击登录按钮")
            return

        logger.info("尝试通过JavaScript触发登录")
        self._trigger_login_via_js()

    def _trigger_login_via_js(self) -> None:
        """通过JavaScript触发登录事件"""
        js_triggers = [
            'document.querySelector("form")?.submit()',
            'document.querySelector(".el-button--primary")?.click()',
            'document.querySelector("button:has-text(\\"登 录\\")")?.click()',
            """const btn = document.querySelector("button"); if(btn && btn.textContent.includes("登")) btn.click();""",
        ]

        for js in js_triggers:
            try:
                self.page.evaluate(js)
                logger.info(f"执行JavaScript: {js}")
                return
            except Exception as e:
                logger.debug(f"JavaScript执行失败: {e}")

        logger.info("尝试按Enter键提交表单")
        self.page.keyboard.press("Enter")

    @allure.step("Perform login with username: {username}")
    def login(self, username: str, password: str, timeout: int = 45000) -> bool:
        """执行完整登录流程，支持重试机制

        Args:
            username: 用户名
            password: 密码
            timeout: 超时时间（毫秒）

        Returns:
            是否登录成功
        """
        import random

        # One retry is sufficient for transient navigation issues. Failed
        # credentials should return promptly instead of polling for 45s three
        # times and then being rerun by pytest again.
        max_retries = 1
        effective_timeout = min(timeout, 15000) if (not username or not password) else min(timeout, 20000)
        for attempt in range(max_retries + 1):
            try:
                self.navigate_to_login()
                self.wait_for_load_state("networkidle")

                if attempt > 0:
                    delay = random.uniform(1, 3)
                    logger.info(f"登录重试 {attempt}/{max_retries}，等待 {delay:.2f} 秒")
                    self.wait_for_poll_interval(int(delay * 1000))

                self.enter_username(username)
                self.enter_password(password)

                self._handle_checkbox()

                self.click_login()

                login_success = False
                polling_interval = 500
                max_polls = max(1, effective_timeout // polling_interval)

                for poll in range(max_polls):
                    if self._is_login_successful():
                        login_success = True
                        break
                    self.wait_for_poll_interval(polling_interval)
                    logger.debug(f"登录检测中，尝试 {poll + 1}/{max_polls}")

                if login_success:
                    logger.info("登录成功")
                    return True

                logger.warning(f"登录失败（尝试 {attempt + 1}）：URL仍包含login或未检测到登录成功标识")

            except Exception as e:
                logger.error(f"登录异常（尝试 {attempt + 1}）: {e}")

            if attempt < max_retries:
                logger.info(f"准备重试登录，第 {attempt + 2} 次尝试")

        return False

    def _handle_checkbox(self) -> None:
        """处理登录页面的复选框（如记住密码等）"""
        checkbox_selectors = [
            ".el-checkbox",
            'input[type="checkbox"]',
            ".el-checkbox__original",
        ]

        for selector in checkbox_selectors:
            try:
                checkbox = self.page.locator(selector)
                if checkbox.count() > 0 and not checkbox.first.is_checked():
                    checkbox.first.click()
                    logger.info(f"勾选复选框: {selector}")
                    break
            except Exception:
                continue

    def _is_login_successful(self) -> bool:
        """判断是否登录成功

        通过多种方式验证：URL变化、页面元素变化、欢迎信息等
        """
        url = self.current_url.lower()

        if "login" not in url and "auth" not in url:
            logger.debug(f"登录成功检测: URL不包含login/auth - {url}")
            return True

        success_indicators = [
            ".sidebar",
            ".navbar",
            ".user-info",
            ".avatar",
            '//*[contains(text(), "欢迎")]',
            '//*[contains(text(), "Dashboard")]',
            '//*[contains(text(), "工作台")]',
            '//*[contains(text(), "首页")]',
            '[data-testid="sidebar"]',
            ".el-menu--collapse",
            ".main-container",
            ".app-container",
            '//*[contains(text(), "系统管理")]',
            '//*[contains(text(), "销售管理")]',
            '//*[contains(text(), "采购管理")]',
            ".el-header",
            ".el-aside",
        ]

        for selector in success_indicators:
            try:
                count = self.page.locator(selector).count()
                if count > 0 and self.page.locator(selector).first.is_visible(timeout=1000):
                    logger.debug(f"登录成功检测: 找到成功标识元素 - {selector} (数量: {count})")
                    return True
            except Exception:
                continue

        try:
            login_btn_count = self.page.locator('button:has-text("登 录")').count()
            if login_btn_count == 0:
                logger.debug("登录成功检测: 登录按钮已消失")
                return True
        except Exception:
            pass

        return False

    @allure.step("Verify login page is displayed")
    def verify_login_page(self) -> None:
        """验证登录页面是否显示"""
        import re

        current_url = self.page.url
        login_indicators = [
            r"/login",
            r"/auth",
            r"/oms-ui/index",
        ]

        found = any(re.search(pattern, current_url) for pattern in login_indicators)
        if not found:
            username_inputs = [
                'input[placeholder="账号"]',
                'input[placeholder="用户名"]',
                'input[placeholder="手机号"]',
            ]
            for selector in username_inputs:
                if self.page.locator(selector).count() > 0:
                    found = True
                    break

        assert found, f"URL不包含登录页面路径，且未找到登录输入框: {current_url}"
        logger.info(f"验证登录页面显示: {current_url}")

    @allure.step("Get login error message")
    def get_error_message(self) -> str:
        """获取登录错误提示信息"""
        error_selectors = [
            ".error-message",
            ".alert-danger",
            'div[role="alert"]',
            '//div[contains(@class, "error")]',
        ]

        for selector in error_selectors:
            try:
                element = self.page.locator(selector)
                if element.is_visible():
                    text = element.text_content() or ""
                    logger.info(f"获取错误信息: {text}")
                    return text
            except Exception:
                continue

        logger.warning("未找到错误信息元素")
        return ""

    @allure.step("Clear credentials")
    def clear_credentials(self) -> None:
        """清空用户名和密码输入框"""
        for selector in self._username_selectors:
            try:
                self.page.locator(selector).fill("")
                break
            except Exception:
                continue

        for selector in self._password_selectors:
            try:
                self.page.locator(selector).fill("")
                break
            except Exception:
                continue

        logger.info("清空登录凭证")

    @allure.step("Verify login failed with error: {expected_error}")
    def verify_login_failed(self, expected_error: str | None = None) -> bool:
        """验证登录失败

        Args:
            expected_error: 期望的错误信息（可选）

        Returns:
            是否验证通过
        """
        error_msg = self.get_error_message()

        if expected_error:
            if expected_error in error_msg:
                logger.info(f"验证登录失败成功: {error_msg}")
                return True
            logger.warning(f"错误信息不匹配: 期望='{expected_error}', 实际='{error_msg}'")
            return False

        if error_msg:
            logger.info(f"检测到登录失败: {error_msg}")
            return True

        logger.warning("未检测到错误信息")
        return False

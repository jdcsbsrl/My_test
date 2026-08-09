"""Login Regression Tests - Validate authentication across environments."""

import os

import pytest
from dotenv import load_dotenv
from playwright.sync_api import Browser, Page

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.drivers.browser_driver import BrowserDriver
from modules.auto_test.pages.login_page import LoginPage

load_dotenv()

USERNAME = os.getenv("TEST_USERNAME")
PASSWORD = os.getenv("TEST_PASSWORD")


@pytest.fixture(scope="function")
def browser() -> Browser:
    """Create a browser instance for each test."""
    driver = BrowserDriver()
    config = get_config()
    browser = driver.start_browser(
        browser=config.get("playwright.browser", "chromium"), headless=True, slow_mo=config.get("playwright.slow_mo", 0)
    )
    yield browser
    driver.shutdown_browser()


@pytest.fixture(scope="function")
def page(browser: Browser) -> Page:
    """Create a new page for each test."""
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    yield page
    context.close()


@pytest.mark.regression
@pytest.mark.auth
@pytest.mark.p0
@pytest.mark.smoke
class TestLoginRegression:
    """Login regression test suite."""

    def test_login_success(self, page: Page) -> None:
        """Test successful login with valid credentials."""
        login_page = LoginPage(page)
        assert login_page.login(USERNAME, PASSWORD), "登录失败"

    def test_login_failure_wrong_password(self, page: Page) -> None:
        """Test login failure with incorrect password."""
        login_page = LoginPage(page)
        result = login_page.login(USERNAME, "wrong_password")
        assert not result, "不应登录成功"

    def test_login_failure_empty_username(self, page: Page) -> None:
        """Test login failure with empty username."""
        login_page = LoginPage(page)
        result = login_page.login("", PASSWORD)
        assert not result, "不应登录成功"

    def test_login_failure_empty_password(self, page: Page) -> None:
        """Test login failure with empty password."""
        login_page = LoginPage(page)
        result = login_page.login(USERNAME, "")
        assert not result, "不应登录成功"

    def test_login_page_display(self, page: Page) -> None:
        """Test login page is displayed correctly."""
        login_page = LoginPage(page)
        login_page.navigate_to_login()
        login_page.verify_login_page()

    def test_login_element_visibility(self, page: Page) -> None:
        """Test login form elements are visible."""
        login_page = LoginPage(page)
        login_page.navigate_to_login()

        for selector in login_page._username_selectors:
            try:
                page.locator(selector).wait_for(timeout=5000)
                break
            except Exception:
                continue
        else:
            pytest.fail("用户名输入框不可见")

        for selector in login_page._password_selectors:
            try:
                page.locator(selector).wait_for(timeout=5000)
                break
            except Exception:
                continue
        else:
            pytest.fail("密码输入框不可见")

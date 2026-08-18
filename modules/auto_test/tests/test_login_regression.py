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
def login_browser() -> Browser:
    """Create a browser instance for each test."""
    driver = BrowserDriver()
    config = get_config()
    browser = driver.start_browser(
        browser=config.get("playwright.browser", "chromium"), headless=True, slow_mo=config.get("playwright.slow_mo", 0)
    )
    yield browser
    driver.shutdown_browser()


@pytest.fixture(scope="function")
def unauthenticated_page(login_browser: Browser) -> Page:
    """Create a new page for each test."""
    context = login_browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    yield page
    context.close()


@pytest.mark.regression
@pytest.mark.auth
@pytest.mark.p0
@pytest.mark.smoke
class TestLoginRegression:
    """Login regression test suite."""

    def test_login_success(self, unauthenticated_page: Page) -> None:
        """Test successful login with valid credentials."""
        login = LoginPage(unauthenticated_page)
        assert login.login(USERNAME, PASSWORD), "登录失败"

    def test_login_failure_wrong_password(self, unauthenticated_page: Page) -> None:
        """Test login failure with incorrect password."""
        login = LoginPage(unauthenticated_page)
        result = login.login(USERNAME, "wrong_password")
        assert not result, "不应登录成功"

    def test_login_failure_empty_username(self, unauthenticated_page: Page) -> None:
        """Test login failure with empty username."""
        login = LoginPage(unauthenticated_page)
        result = login.login("", PASSWORD)
        assert not result, "不应登录成功"

    def test_login_failure_empty_password(self, unauthenticated_page: Page) -> None:
        """Test login failure with empty password."""
        login = LoginPage(unauthenticated_page)
        result = login.login(USERNAME, "")
        assert not result, "不应登录成功"

    def test_login_page_display(self, unauthenticated_page: Page) -> None:
        """Test login page is displayed correctly."""
        login = LoginPage(unauthenticated_page)
        login.navigate_to_login()
        login.verify_login_page()

    def test_login_element_visibility(self, unauthenticated_page: Page) -> None:
        """Test login form elements are visible."""
        login = LoginPage(unauthenticated_page)
        login.navigate_to_login()
        assert login.has_username_input(), "用户名输入框不可见"
        assert login.has_password_input(), "密码输入框不可见"

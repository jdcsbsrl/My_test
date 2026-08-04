"""Shared pytest fixtures for auto_test module."""

import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from modules.auto_test.core.config_manager import ConfigManager, get_config
from modules.auto_test.core.test_data_factory import (
    DatabaseDataGenerator,
    EnhancedTestDataFactory,
    SchemaBasedFactory,
    TestDataFactory,
)
from modules.auto_test.core.token_manager import TokenManager, get_token_manager
from modules.auto_test.drivers.browser_driver import BrowserDriver
from modules.auto_test.pages.login_page import LoginPage

load_dotenv()
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(__file__).resolve().parents[2] / "browsers")

USERNAME = os.getenv("TEST_USERNAME")
PASSWORD = os.getenv("TEST_PASSWORD")

if not USERNAME or not PASSWORD:
    raise RuntimeError(
        "TEST_USERNAME and/or TEST_PASSWORD not set. "
        "Ensure .env file exists or environment variables are configured."
    )


@pytest.fixture(scope="session")
def config_manager() -> ConfigManager:
    """Provide a global configuration manager instance."""
    return get_config()


@pytest.fixture(scope="session")
def test_data_factory() -> TestDataFactory:
    """Provide a test data factory for generating test data (DB-backed when available)."""
    return EnhancedTestDataFactory()


@pytest.fixture(scope="session")
def database_data_generator() -> DatabaseDataGenerator:
    """Provide a database-backed data generator for real business data."""
    return DatabaseDataGenerator()


@pytest.fixture(scope="session")
def schema_factory() -> SchemaBasedFactory:
    """Provide a schema-based data factory."""
    return SchemaBasedFactory()


@pytest.fixture(scope="session")
def browser(config_manager: ConfigManager) -> Browser:
    """Reuse one browser process; function-scoped contexts preserve test isolation."""
    driver = BrowserDriver()
    browser = driver.start_browser(
        browser=config_manager.get("playwright.browser", "chromium"),
        headless=config_manager.get("playwright.headless", True),
        slow_mo=config_manager.get("playwright.slow_mo", 0),
    )
    yield browser
    driver.shutdown_browser()


@pytest.fixture(scope="function")
def context(
    browser: Browser, config_manager: ConfigManager, authenticated_storage_state: str
) -> BrowserContext:
    """Create a new browser context for each test function."""
    viewport = config_manager.get("playwright.viewport", {"width": 1920, "height": 1080})
    context_options = {
        "viewport": viewport,
        "accept_downloads": True,
        "record_video_dir": None,
        "record_video_size": None,
        "storage_state": authenticated_storage_state,
    }

    video_config = config_manager.get("playwright.video", "off")
    if video_config in ("on", "retain-on-failure"):
        context_options["record_video_dir"] = "reports/videos"
        context_options["record_video_size"] = viewport

    context = browser.new_context(**context_options)

    trace_config = config_manager.get("playwright.trace", "off")
    if trace_config in ("on", "retain-on-failure", "on-first-retry"):
        context.tracing.start(screenshots=True, snapshots=True, sources=True)

    yield context

    if trace_config != "off":
        os.makedirs("reports/traces", exist_ok=True)
        trace_path = f"reports/traces/test_trace_{uuid.uuid4().hex[:8]}.zip"
        context.tracing.stop(path=trace_path)
    context.close()


@pytest.fixture(scope="session")
def authenticated_storage_state(
    browser: Browser, config_manager: ConfigManager, tmp_path_factory
) -> str:
    """Login once per shard and reuse the resulting isolated authentication state."""
    auth_dir = tmp_path_factory.mktemp("playwright-auth")
    auth_file = auth_dir / "state.json"
    auth_context = browser.new_context(
        viewport=config_manager.get("playwright.viewport", {"width": 1920, "height": 1080})
    )
    auth_page = auth_context.new_page()
    try:
        if not LoginPage(auth_page).login(USERNAME, PASSWORD):
            pytest.fail("Unable to create authenticated browser state")
        auth_context.storage_state(path=str(auth_file))
    finally:
        auth_context.close()
    return str(auth_file)


@pytest.fixture(scope="function")
def page(context: BrowserContext) -> Page:
    """Create a new page for each test function."""
    page = context.new_page()
    yield page
    page.close()


@pytest.fixture(scope="function")
def logged_in_page(page: Page) -> Page:
    """Provide a page that is already logged in.

    This fixture is useful for tests that require authentication.
    """
    page.goto(get_config().base_url)
    page.wait_for_load_state("domcontentloaded")
    if "/login" in page.url:
        pytest.fail("Cached authentication state is invalid")
    yield page


@pytest.fixture(scope="function")
def login_page(page: Page) -> LoginPage:
    """Provide a LoginPage instance for login-related tests."""
    return LoginPage(page)


@pytest.fixture(scope="session")
def test_user_credentials() -> dict[str, str]:
    """Provide test user credentials."""
    return {
        "username": USERNAME,
        "password": PASSWORD,
    }


@pytest.fixture(scope="function")
def temp_report_dir(tmp_path):
    """Create a temporary directory for test reports."""
    report_dir = tmp_path / "reports"
    report_dir.mkdir(exist_ok=True)
    return report_dir


@pytest.fixture(scope="session")
def api_base_url(config_manager: ConfigManager) -> str:
    """Provide the API base URL from configuration."""
    return config_manager.api_base_url


@pytest.fixture(scope="session")
def ui_base_url(config_manager: ConfigManager) -> str:
    """Provide the UI base URL from configuration."""
    return config_manager.base_url


@pytest.fixture(scope="session")
def token_manager() -> TokenManager:
    """Provide a TokenManager instance for storing and retrieving authentication tokens."""
    return get_token_manager()


@pytest.fixture(scope="session")
def login_response(
    ui_base_url: str,
    test_user_credentials: dict[str, str],
    config_manager: ConfigManager,
) -> dict:
    """Provide the full login response containing token and user information.

    Uses Playwright to perform a real browser login and captures the API response.
    """
    login_result = {}

    def handle_response(response):
        if "/auth/login" in response.url:
            try:
                login_result["response"] = response.json()
                request_headers = response.request.all_headers()
                login_result["clientid"] = request_headers.get("clientid") or request_headers.get("client-id")
            except Exception:
                pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=config_manager.get("playwright.headless", True))
        try:
            page = browser.new_page(viewport=config_manager.get("playwright.viewport", {"width": 1920, "height": 1080}))
            page.on("response", handle_response)

            page.goto(ui_base_url)
            page.wait_for_load_state("networkidle")

            login_page = LoginPage(page)
            login_page.login(test_user_credentials["username"], test_user_credentials["password"])

            if "response" not in login_result:
                pytest.fail("Failed to capture login API response")

            login_result["response"]["_cookies"] = page.context.cookies()
            login_result["response"]["_clientid"] = login_result.get("clientid")

            return login_result["response"]

        except Exception as e:
            pytest.fail(f"Failed to get login response: {e}")
        finally:
            browser.close()


@pytest.fixture(scope="session")
def login_token(login_response: dict, token_manager: TokenManager, config_manager: ConfigManager) -> str:
    """Provide the authentication token for API requests.

    The token is cached using TokenManager to avoid repeated login during the test session.

    Returns:
        str: The access token for API authentication
    """
    if login_response.get("code") == 200:
        data = login_response.get("data") or {}
        token = data.get("token") or data.get("access_token")
        if token:
            token_manager.save_token(
                env=config_manager.env, token=str(token), username=USERNAME, expires_in=data.get("expire_in", 7200)
            )
            return str(token)
    pytest.fail("Failed to extract token from login response")


@pytest.fixture(scope="function")
def http_client():
    """Provide an HTTP client for API testing."""
    session = requests.Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def authenticated_http_client(http_client, login_token: str, login_response: dict) -> requests.Session:
    """Provide an HTTP client with authentication token already set.

    The Authorization header is automatically added to all requests.

    Returns:
        requests.Session: HTTP session with Authorization header
    """
    clientid = (
        login_response.get("_clientid")
        or os.getenv("TEST_TEST_CLIENTID")
        or os.getenv("TEST_CLIENTID")
    )
    headers = {"Authorization": f"Bearer {login_token}", "Content-Type": "application/json"}
    if clientid:
        headers["clientid"] = clientid
    http_client.headers.update(headers)
    for cookie in login_response.get("_cookies", []):
        http_client.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain"), path=cookie.get("path", "/"))
    yield http_client


@pytest.fixture(scope="function")
def auto_cleanup():
    """Provide a cleanup mechanism for test artifacts."""
    cleanup_items = []

    def add_cleanup(func, *args, **kwargs):
        cleanup_items.append((func, args, kwargs))

    yield add_cleanup

    for func, args, kwargs in reversed(cleanup_items):
        try:
            func(*args, **kwargs)
        except Exception:
            pass


@pytest.fixture(scope="function")
def screenshot_helper(page: Page):
    """Provide a helper function for taking screenshots during tests."""

    def take_screenshot(name: str):
        os.makedirs("reports/screenshots", exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = f"reports/screenshots/{name}_{timestamp}_{uuid.uuid4().hex[:6]}.png"
        page.screenshot(path=path, full_page=True)
        return path

    return take_screenshot

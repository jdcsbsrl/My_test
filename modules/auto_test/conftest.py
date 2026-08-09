"""Shared pytest fixtures for auto_test module."""

import os
import json
import sys
import time
import uuid

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
from modules.auto_test.core.test_data_lifecycle import TestDataLifecycleManager
from modules.auto_test.drivers.browser_driver import BrowserDriver
from modules.auto_test.pages.login_page import LoginPage

load_dotenv()

USERNAME = os.getenv("TEST_USERNAME")
PASSWORD = os.getenv("TEST_PASSWORD")
TEST_RUN_ID = os.getenv("TEST_RUN_ID", uuid.uuid4().hex)
_TEST_ATTEMPTS: dict[str, int] = {}
_TEST_RESULTS: list[dict] = []

if not USERNAME or not PASSWORD:
    raise RuntimeError(
        "TEST_USERNAME and/or TEST_PASSWORD not set. "
        "Ensure .env file exists or environment variables are configured."
    )


def pytest_configure(config: pytest.Config) -> None:
    """Publish stable metadata for every local and CI test run."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")
    metadata = {
        "run_id": TEST_RUN_ID,
        "environment": os.getenv("TEST_ENV", "test"),
        "browser": os.getenv("PLAYWRIGHT_BROWSER_CHANNEL", "chromium"),
        "commit_sha": os.getenv("GITHUB_SHA", "local"),
    }
    config._test_run_metadata = metadata
    os.makedirs("reports", exist_ok=True)
    with open("reports/test-run.json", "w", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Record attempts and identify tests that pass only after a rerun."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call":
        return

    _TEST_ATTEMPTS[item.nodeid] = _TEST_ATTEMPTS.get(item.nodeid, 0) + 1
    attempts = _TEST_ATTEMPTS[item.nodeid]
    metadata = getattr(item.config, "_test_run_metadata", {})
    payload = {
        **metadata,
        "nodeid": item.nodeid,
        "outcome": report.outcome,
        "attempt": attempts,
        "failure_category": _classify_failure(report) if report.failed else None,
    }
    if attempts > 1 and report.outcome == "passed":
        payload["status"] = "flaky_passed"
        report.user_properties.append(("flaky_passed", "true"))
        try:
            import allure

            allure.attach(
                json.dumps(payload, ensure_ascii=False, indent=2),
                "flaky-test-attempt",
                allure.attachment_type.JSON,
            )
        except Exception:
            pass
    with open("reports/test-attempts.jsonl", "a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False) + "\n")
    _TEST_RESULTS.append(payload)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Write a compact result summary for CI and local triage."""
    summary = {"passed": 0, "failed": 0, "flaky_passed": 0, "categories": {}}
    for result in _TEST_RESULTS:
        if result.get("status") == "flaky_passed":
            summary["flaky_passed"] += 1
        elif result.get("outcome") == "passed":
            summary["passed"] += 1
        elif result.get("outcome") == "failed":
            summary["failed"] += 1
        category = result.get("failure_category")
        if category:
            summary["categories"][category] = summary["categories"].get(category, 0) + 1
    summary.update({"exitstatus": exitstatus, "run_id": TEST_RUN_ID})
    with open("reports/test-summary.json", "w", encoding="utf-8") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)


def _classify_failure(report: pytest.TestReport) -> str:
    text = str(getattr(report, "longrepr", "")).lower()
    if "timeout" in text:
        return "timeout"
    if any(token in text for token in ("401", "403", "authentication", "login")):
        return "authentication_failure"
    if any(token in text for token in ("connectionerror", "connecttimeout", "502", "503", "504")):
        return "environment_failure"
    if any(token in text for token in ("assertionerror", "assert ")):
        return "product_or_test_assertion"
    return "unknown"


@pytest.fixture(scope="session")
def config_manager() -> ConfigManager:
    """Provide a global configuration manager instance."""
    return get_config()


@pytest.fixture(scope="session")
def test_data_factory() -> TestDataFactory:
    """Provide a test data factory for generating test data (DB-backed when available)."""
    return EnhancedTestDataFactory()


@pytest.fixture(scope="function")
def data_lifecycle(config_manager: ConfigManager):
    """Track test-created data and always attempt cleanup after the test."""
    manager = TestDataLifecycleManager(env=config_manager.env)
    yield manager
    manager.execute_cleanup()


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
def authenticated_http_client(http_client, login_token: str) -> requests.Session:
    """Provide an HTTP client with authentication token already set.

    The Authorization header is automatically added to all requests.

    Returns:
        requests.Session: HTTP session with Authorization header
    """
    http_client.headers.update({"Authorization": f"Bearer {login_token}", "Content-Type": "application/json"})
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

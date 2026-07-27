from unittest.mock import Mock

import pytest

from modules.auto_test.drivers.browser_driver import BrowserDriver


pytestmark = pytest.mark.unit


class FakeConfig:
    def __init__(self, values=None):
        self.values = values or {}

    def get(self, key, default=None):
        return self.values.get(key, default)


@pytest.fixture
def driver(monkeypatch):
    monkeypatch.setattr("modules.auto_test.drivers.browser_driver.get_config", lambda: FakeConfig())
    return BrowserDriver()


def test_start_browser_launches_requested_browser(monkeypatch, driver):
    browser = Mock()
    browser_type = Mock()
    browser_type.launch.return_value = browser
    playwright = Mock()
    playwright.chromium = browser_type
    starter = Mock()
    starter.start.return_value = playwright
    monkeypatch.setattr("modules.auto_test.drivers.browser_driver.sync_playwright", lambda: starter)
    monkeypatch.delenv("PLAYWRIGHT_CDP_ENDPOINT", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_BROWSER_CHANNEL", raising=False)

    result = driver.start_browser(browser="chromium", headless=True, slow_mo=25)

    assert result is browser
    browser_type.launch.assert_called_once_with(headless=True, slow_mo=25)


def test_start_browser_reuses_existing_browser(driver):
    existing = Mock()
    driver.browser = existing

    assert driver.start_browser(browser="chromium", headless=True, slow_mo=0) is existing


def test_start_browser_connects_over_cdp(monkeypatch, driver):
    browser = Mock()
    playwright = Mock()
    playwright.chromium.connect_over_cdp.return_value = browser
    starter = Mock()
    starter.start.return_value = playwright
    monkeypatch.setattr("modules.auto_test.drivers.browser_driver.sync_playwright", lambda: starter)
    monkeypatch.setenv("PLAYWRIGHT_CDP_ENDPOINT", "http://localhost:9222")

    result = driver.start_browser(browser="chromium", headless=False, slow_mo=0)

    assert result is browser
    playwright.chromium.connect_over_cdp.assert_called_once_with("http://localhost:9222")


def test_start_browser_rejects_channel_for_non_chromium(monkeypatch, driver):
    playwright = Mock()
    starter = Mock()
    starter.start.return_value = playwright
    monkeypatch.setattr("modules.auto_test.drivers.browser_driver.sync_playwright", lambda: starter)
    monkeypatch.delenv("PLAYWRIGHT_CDP_ENDPOINT", raising=False)
    monkeypatch.setenv("PLAYWRIGHT_BROWSER_CHANNEL", "msedge")

    with pytest.raises(ValueError):
        driver.start_browser(browser="firefox", headless=True, slow_mo=0)


def test_new_context_and_page_uses_video_and_trace_options(monkeypatch):
    config = FakeConfig(
        {
            "playwright.viewport": {"width": 1280, "height": 720},
            "playwright.video": "on",
            "playwright.trace": "retain-on-failure",
        }
    )
    monkeypatch.setattr("modules.auto_test.drivers.browser_driver.get_config", lambda: config)
    driver = BrowserDriver()
    context = Mock()
    page = Mock()
    context.new_page.return_value = page
    browser = Mock()
    browser.new_context.return_value = context
    driver.browser = browser

    result = driver.new_context_and_page()

    assert result == (context, page)
    browser.new_context.assert_called_once_with(
        viewport={"width": 1280, "height": 720},
        accept_downloads=True,
        record_video_dir="reports/videos",
        record_video_size={"width": 1280, "height": 720},
    )
    context.tracing.start.assert_called_once_with(screenshots=True, snapshots=True, sources=True)


def test_new_context_and_page_requires_started_browser(driver):
    with pytest.raises(RuntimeError):
        driver.new_context_and_page()


def test_close_context_stops_trace_when_path_is_given(monkeypatch):
    monkeypatch.setattr(
        "modules.auto_test.drivers.browser_driver.get_config",
        lambda: FakeConfig({"playwright.trace": "on"}),
    )
    driver = BrowserDriver()
    context = Mock()

    driver.close_context(context, trace_path="reports/traces/test.zip")

    context.tracing.stop.assert_called_once_with(path="reports/traces/test.zip")
    context.close.assert_called_once_with()


def test_shutdown_browser_closes_browser_and_playwright(driver):
    browser = Mock()
    playwright = Mock()
    driver.browser = browser
    driver._playwright = playwright

    driver.shutdown_browser()

    browser.close.assert_called_once_with()
    playwright.stop.assert_called_once_with()
    assert driver.browser is None
    assert driver._playwright is None

"""Browser-level fault injection on local HTML; no external business mutations."""

from modules.auto_test.core.self_healing import LocatorContext, SelfHealingConfig, SelfHealingLocator
from modules.auto_test.drivers.browser_driver import BrowserDriver


def test_changed_locator_and_ambiguous_replacement(tmp_path):
    driver = BrowserDriver()
    try:
        browser = driver.start_browser(browser="chromium", headless=True, slow_mo=0)
        page = browser.new_page()
        page.set_content('<button id="old-search">Search</button><output>idle</output>')
        assert page.locator("#old-search").count() == 1
        # Simulate a deployment that changes CSS while retaining the accessible action name.
        page.set_content(
            "<button id=\"new-search\" onclick=\"document.querySelector('output').textContent='found'\">"
            "Search</button><output>idle</output>"
        )
        healing = SelfHealingLocator(
            page,
            SelfHealingConfig(
                enabled=True,
                strategies=["exact_selector", "role_name"],
                timeout_ms=100,
                attach_allure=False,
                screenshot_on_success=False,
                metrics_enabled=False,
                history_path=str(tmp_path / "healing.jsonl"),
            ),
            env="uat",
        )
        context = LocatorContext(selector="#old-search", role="button", names=["Search"], description="search")
        assert healing.execute("click", context, lambda locator: locator.click())
        assert page.locator("output").inner_text() == "found"
        assert page._test_erp_healing_events[0]["needs_review"] is True
        # Two replacements must not result in choosing the first element silently.
        page.set_content("<button>Search</button><button>Search</button><output>idle</output>")
        assert not healing.execute("click", context, lambda locator: locator.click())
        assert page.locator("output").inner_text() == "idle"
    finally:
        driver.shutdown_browser()

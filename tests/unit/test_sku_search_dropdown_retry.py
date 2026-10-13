"""Regression coverage for transient SKU dropdown loading failures."""

from types import SimpleNamespace

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from modules.auto_test.pages.sku_search_page import SKUSearchPage

pytestmark = pytest.mark.unit


def test_first_available_option_retries_after_dropdown_timeout(monkeypatch):
    page = SKUSearchPage.__new__(SKUSearchPage)
    escaped = []
    page.page = SimpleNamespace(keyboard=SimpleNamespace(press=escaped.append))
    attempts = []
    waits = []

    monkeypatch.setattr(page, "_open_dropdown_by_placeholder", lambda _: attempts.append(1) or True)

    def wait_for_options():
        waits.append(1)
        if len(waits) == 1:
            raise PlaywrightTimeoutError("dropdown loading")

    monkeypatch.setattr(page, "_wait_for_visible_dropdown_options", wait_for_options)
    monkeypatch.setattr(page, "_get_visible_dropdown_options", lambda: ["产品品类 A"])
    monkeypatch.setattr(page, "wait_for_poll_interval", lambda _: None)

    assert page.get_first_available_dropdown_option("产品品类") == "产品品类 A"
    assert len(attempts) == 2
    assert escaped == ["Escape", "Escape"]


def test_first_available_option_fails_after_bounded_retries(monkeypatch):
    page = SKUSearchPage.__new__(SKUSearchPage)
    page.page = SimpleNamespace(keyboard=SimpleNamespace(press=lambda _: None))
    attempts = []
    monkeypatch.setattr(page, "_open_dropdown_by_placeholder", lambda _: attempts.append(1) or True)
    monkeypatch.setattr(
        page,
        "_wait_for_visible_dropdown_options",
        lambda: (_ for _ in ()).throw(PlaywrightTimeoutError("dropdown loading")),
    )
    monkeypatch.setattr(page, "wait_for_poll_interval", lambda _: None)

    with pytest.raises(ValueError, match="产品品类"):
        page.get_first_available_dropdown_option("产品品类")
    assert len(attempts) == 3

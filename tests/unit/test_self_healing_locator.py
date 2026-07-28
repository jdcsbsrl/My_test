from types import SimpleNamespace

import json

import pytest

from modules.auto_test.core import self_healing as self_healing_module
from modules.auto_test.core.self_healing import (
    HealingHistoryCase,
    LocatorContext,
    SelfHealingConfig,
    SelfHealingHistoryStore,
    SelfHealingLocator,
    load_self_healing_config,
)
from modules.auto_test.pages import base_page as base_page_module
from modules.auto_test.pages.base_page import BasePage


pytestmark = pytest.mark.unit


class FakeLocator:
    def __init__(self, selector: str, *, count: int = 1, fails: bool = False) -> None:
        self.selector = selector
        self._count = count
        self.fails = fails
        self.first = self
        self.calls = []

    def count(self):
        if self.fails:
            return 0
        return self._count

    def wait_for(self, timeout=0):
        self.calls.append(("wait", timeout))
        if self.fails or self._count == 0:
            raise RuntimeError("missing")

    def click(self):
        self.calls.append("click")
        if self.fails or self._count == 0:
            raise RuntimeError("missing")

    def fill(self, value):
        self.calls.append(("fill", value))
        if self.fails or self._count == 0:
            raise RuntimeError("missing")


class FakePage:
    def __init__(self) -> None:
        self.url = "https://example.test"
        self.locators = {
            "#old": FakeLocator("#old", count=0, fails=True),
            "#new": FakeLocator("#new"),
            "#many": FakeLocator("#many", count=2),
        }
        self.calls = []

    def locator(self, selector):
        self.calls.append(("locator", selector))
        return self.locators.get(selector, FakeLocator(selector, count=0, fails=True))

    def get_by_role(self, role, name=None):
        self.calls.append(("role", role, name))
        if role == "button" and name == "Save":
            return FakeLocator(f"{role}:{name}")
        return FakeLocator(f"{role}:{name}", count=0, fails=True)

    def get_by_text(self, text):
        self.calls.append(("text", text))
        if text == "Submit":
            return FakeLocator(text)
        return FakeLocator(text, count=0, fails=True)

    def screenshot(self, path, full_page=True):
        self.calls.append(("screenshot", path, full_page))


def _config(**overrides):
    values = {
        "enabled": True,
        "attach_allure": False,
        "screenshot_on_success": False,
        "metrics_enabled": False,
        "history_enabled": False,
        "strategies": ["exact_selector", "selector_chain", "role_name", "text"],
    }
    values.update(overrides)
    return SelfHealingConfig(**values)


@pytest.fixture(autouse=True)
def reset_breaker():
    SelfHealingLocator._breaker = None
    yield
    SelfHealingLocator._breaker = None


def test_selector_chain_heals_to_first_working_selector():
    page = FakePage()
    healer = SelfHealingLocator(page, _config(), env="test")

    result = healer.locate(LocatorContext(selector="#old", selectors=["#old", "#new"]), timeout=5)

    assert result.locator is page.locators["#new"]
    assert result.healed
    assert result.strategy == "selector_chain"


def test_ambiguous_match_is_rejected():
    page = FakePage()
    healer = SelfHealingLocator(page, _config(strategies=["exact_selector"]), env="test")

    result = healer.locate(LocatorContext(selector="#many"), timeout=5)

    assert result.locator is None
    assert result.error == "no self-healing strategy matched"


def test_missing_candidate_uses_not_found_error():
    page = FakePage()
    healer = SelfHealingLocator(page, _config(strategies=["exact_selector"]), env="test")

    result = healer._candidate(page.locators["#old"], "exact_selector", "#old", False, timeout=5)

    assert result.locator is None
    assert result.error == "not found"


def test_role_and_text_strategies_are_available():
    page = FakePage()
    healer = SelfHealingLocator(page, _config(strategies=["role_name", "text"]), env="test")

    role_result = healer.locate(LocatorContext(role="button", names=["Save"]), timeout=5)
    text_result = healer.locate(LocatorContext(text="Submit"), timeout=5)

    assert role_result.locator is not None
    assert role_result.strategy == "role_name"
    assert text_result.locator is not None
    assert text_result.strategy == "text"


def test_base_page_try_click_uses_self_healing_when_enabled(monkeypatch):
    monkeypatch.setattr(
        base_page_module,
        "get_config",
        lambda: SimpleNamespace(base_url="https://example.test", env="test"),
    )
    page = FakePage()
    base = BasePage(page)
    base.self_healing.config = _config()

    assert base.try_click(["#old", "#new"], timeout=5)
    assert "click" in page.locators["#new"].calls


def test_enabled_requires_allowed_env_or_env_override(monkeypatch):
    page = FakePage()
    config = _config(enabled=False)

    healer = SelfHealingLocator(page, config, env="test")
    assert not healer.enabled

    monkeypatch.setenv("SELF_HEALING_ENABLED", "true")
    assert healer.enabled

    production_healer = SelfHealingLocator(page, _config(enabled=True), env="production")
    assert not production_healer.enabled


def test_load_config_falls_back_to_example_yaml(tmp_path):
    config_path = tmp_path / "self_healing.yaml"
    example_path = tmp_path / "self_healing.example.yaml"
    example_path.write_text(
        """
enabled: true
allowed_envs: [test]
max_attempts_per_action: 3
max_heals_per_page: 2
strict_unique_match: false
attach_allure: false
screenshot_on_success: false
metrics_enabled: false
history_enabled: true
history_path: custom/history.jsonl
prefer_history: false
min_history_successes: 3
timeout_ms: 1234
strategies: [text]
circuit_breaker:
  failure_threshold: 2
  cooldown_seconds: 9
""",
        encoding="utf-8",
    )

    config = load_self_healing_config(config_path)

    assert config.enabled
    assert config.allowed_envs == ["test"]
    assert config.max_attempts_per_action == 3
    assert config.max_heals_per_page == 2
    assert not config.strict_unique_match
    assert config.timeout_ms == 1234
    assert config.strategies == ["text"]
    assert config.failure_threshold == 2
    assert config.cooldown_seconds == 9
    assert config.history_enabled
    assert config.history_path == "custom/history.jsonl"
    assert not config.prefer_history
    assert config.min_history_successes == 3


def test_metrics_event_is_written_to_jsonl(tmp_path):
    page = FakePage()
    config = _config(metrics_enabled=True, metrics_root=str(tmp_path))
    healer = SelfHealingLocator(page, config, env="test")

    assert healer.execute(
        "try_click",
        LocatorContext(selector="#old", selectors=["#old", "#new"]),
        lambda locator: locator.click(),
        timeout=5,
    )

    metrics_file = tmp_path / "reports" / "harness_metrics" / "events.jsonl"
    event = json.loads(metrics_file.read_text(encoding="utf-8").splitlines()[0])
    assert event["type"] == "self_healing"
    assert event["action"] == "try_click"
    assert event["healed"] is True
    assert event["success"] is True
    assert event["selector"] == "#new"


def test_allure_attachment_and_screenshot_are_recorded(monkeypatch):
    page = FakePage()
    attachments = []
    files = []

    class FakeAttach:
        def __call__(self, *args, **kwargs):
            attachments.append(args)

        def file(self, *args, **kwargs):
            files.append(args)

    monkeypatch.setattr(self_healing_module.allure, "attach", FakeAttach())
    config = _config(attach_allure=True, screenshot_on_success=True)
    healer = SelfHealingLocator(page, config, env="test")

    assert healer.execute(
        "try_click",
        LocatorContext(selector="#old", selectors=["#old", "#new"]),
        lambda locator: locator.click(),
        timeout=5,
    )

    assert attachments
    assert files
    assert any(call[0] == "screenshot" for call in page.calls)


def test_max_heals_per_page_limits_additional_self_healing():
    page = FakePage()
    config = _config(max_heals_per_page=1)
    healer = SelfHealingLocator(page, config, env="test")

    first = healer.locate(LocatorContext(selector="#old", selectors=["#old", "#new"]), timeout=5)
    second = healer.locate(LocatorContext(selector="#old", selectors=["#old", "#new"]), timeout=5)

    assert first.locator is not None
    assert first.healed
    assert second.locator is None
    assert second.strategy == "heal_limit"


def test_history_store_records_reviewable_cases_and_summary(tmp_path):
    history = SelfHealingHistoryStore(tmp_path / "history.jsonl")

    history.record(
        HealingHistoryCase(
            key="save-button",
            action="click",
            strategy="selector_chain",
            selector="#new",
            original_selector="#old",
            description="Save",
            success=True,
            healed=True,
            candidate_count=1,
            error=None,
            url="https://example.test",
            approved=True,
        )
    )

    selectors = history.successful_selectors("save-button")
    summary = history.summarize()

    assert selectors == ["#new"]
    assert summary == {"total": 1, "success": 1, "failed": 0, "healed": 1, "needs_review": 1}


def test_execute_records_history_for_success_and_failure(tmp_path):
    page = FakePage()
    config = _config(history_enabled=True, history_path=str(tmp_path / "history.jsonl"))
    healer = SelfHealingLocator(page, config, env="test")

    assert healer.execute(
        "try_click",
        LocatorContext(selector="#old", selectors=["#old", "#new"], description="Save"),
        lambda locator: locator.click(),
        timeout=5,
    )
    assert not healer.execute(
        "try_click",
        LocatorContext(selector="#missing", selectors=["#missing"], description="Missing"),
        lambda locator: locator.click(),
        timeout=5,
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["success"] is True
    assert events[0]["needs_review"] is True
    assert events[0]["selector"] == "#new"
    assert len(events) == 1


def test_history_strategy_reuses_previous_successful_selector(tmp_path):
    page = FakePage()
    history_path = tmp_path / "history.jsonl"
    history = SelfHealingHistoryStore(history_path)
    history.record(
        HealingHistoryCase(
            key="Save",
            action="try_click",
            strategy="selector_chain",
            selector="#new",
            original_selector="#old",
            description="Save",
            success=True,
            healed=True,
            approved=True,
            url="https://example.test",
        )
    )
    config = _config(
        history_enabled=True,
        history_path=str(history_path),
        prefer_history=True,
        strategies=["selector_chain"],
    )
    healer = SelfHealingLocator(page, config, env="test")

    result = healer.locate(LocatorContext(selector="#old", selectors=["#old"], description="Save"), timeout=5)

    assert result.locator is page.locators["#new"]
    assert result.strategy == "history"
    assert result.healed


def test_history_strategy_requires_approved_review_status(tmp_path):
    page = FakePage()
    history_path = tmp_path / "history.jsonl"
    history = SelfHealingHistoryStore(history_path)
    history.record(
        HealingHistoryCase(
            key="Save",
            action="try_click",
            strategy="selector_chain",
            selector="#new",
            original_selector="#old",
            description="Save",
            success=True,
            healed=True,
            approved=False,
            url="https://example.test",
        )
    )
    config = _config(history_enabled=True, history_path=str(history_path), prefer_history=True)
    healer = SelfHealingLocator(page, config, env="test")

    result = healer.locate(LocatorContext(selector="#old", selectors=["#old"], description="Save"), timeout=5)

    assert result.strategy != "history"


def test_history_min_successes_filters_low_confidence_selectors(tmp_path):
    history_path = tmp_path / "history.jsonl"
    history = SelfHealingHistoryStore(history_path)
    history.record(
        HealingHistoryCase(
            key="Save",
            action="try_click",
            strategy="selector_chain",
            selector="#new",
            original_selector="#old",
            description="Save",
            success=True,
            healed=True,
            approved=True,
            url="https://example.test",
        )
    )

    assert history.successful_selectors("Save", min_successes=2) == []
    assert history.successful_selectors("Save", min_successes=1) == ["#new"]


def test_history_excludes_non_healed_successes(tmp_path):
    history = SelfHealingHistoryStore(tmp_path / "history.jsonl")
    history.record(
        HealingHistoryCase(
            key="Save",
            action="click",
            strategy="exact_selector",
            selector="#old",
            original_selector="#old",
            description="Save",
            success=True,
            healed=False,
            approved=True,
            url="https://example.test",
        )
    )

    assert history.successful_selectors("Save") == []


def test_operation_failure_records_failure_without_reuse(tmp_path):
    page = FakePage()
    config = _config(history_enabled=True, history_path=str(tmp_path / "history.jsonl"))
    healer = SelfHealingLocator(page, config, env="test")

    assert not healer.execute(
        "try_click",
        LocatorContext(selector="#old", selectors=["#old", "#new"], description="Save"),
        lambda locator: (_ for _ in ()).throw(RuntimeError("click failed")),
        timeout=5,
    )

    events = [
        json.loads(line)
        for line in (tmp_path / "history.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0]["success"] is False
    assert events[0]["needs_review"] is False
    assert SelfHealingHistoryStore(tmp_path / "history.jsonl").successful_selectors("Save") == []

"""Self-healing UI locator support for Playwright page objects."""

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import allure
import yaml
from playwright.sync_api import Locator, Page

from modules.auto_test.core.config_manager import EnvironmentType
from modules.auto_test.core.harness_metrics import HarnessMetricsRecorder, default_metrics_path, metrics_enabled
from modules.auto_test.core.logger import get_logger

logger = get_logger()


DEFAULT_STRATEGIES = ["exact_selector", "selector_chain", "role_name", "text", "semantic_attr", "dom_text"]


@dataclass
class SelfHealingConfig:
    enabled: bool = False
    allowed_envs: list[str] = field(default_factory=lambda: ["test", "test_env", "uat"])
    max_attempts_per_action: int = 6
    max_heals_per_page: int = 20
    strict_unique_match: bool = True
    attach_allure: bool = True
    screenshot_on_success: bool = True
    metrics_enabled: bool = True
    timeout_ms: int = 10000
    strategies: list[str] = field(default_factory=lambda: DEFAULT_STRATEGIES.copy())
    failure_threshold: int = 5
    cooldown_seconds: int = 300
    metrics_root: str | None = None


@dataclass
class LocatorContext:
    selector: str | None = None
    selectors: list[str] = field(default_factory=list)
    role: str | None = None
    names: list[str] = field(default_factory=list)
    text: str | None = None
    description: str | None = None
    semantic_attrs: dict[str, str] = field(default_factory=dict)


@dataclass
class HealingResult:
    locator: Locator | None
    healed: bool
    strategy: str
    selector: str | None = None
    candidate_count: int | None = None
    error: str | None = None


class SelfHealingCircuitBreaker:
    def __init__(self, failure_threshold: int, cooldown_seconds: int) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(1, cooldown_seconds)
        self._failures: dict[str, tuple[int, float]] = {}

    def is_open(self, key: str) -> bool:
        count, last_failure = self._failures.get(key, (0, 0.0))
        if count < self.failure_threshold:
            return False
        if time.time() - last_failure > self.cooldown_seconds:
            self._failures.pop(key, None)
            return False
        return True

    def record_success(self, key: str) -> None:
        self._failures.pop(key, None)

    def record_failure(self, key: str) -> None:
        count, _ = self._failures.get(key, (0, 0.0))
        self._failures[key] = (count + 1, time.time())


class SelfHealingLocator:
    """Strategy cascade for finding a single safe Playwright locator."""

    _breaker: SelfHealingCircuitBreaker | None = None

    def __init__(self, page: Page, config: SelfHealingConfig | None = None, *, env: str = "test") -> None:
        self.page = page
        self.config = config or load_self_healing_config()
        self.env = env
        self.heal_count = 0
        if SelfHealingLocator._breaker is None:
            SelfHealingLocator._breaker = SelfHealingCircuitBreaker(
                self.config.failure_threshold, self.config.cooldown_seconds
            )

    @property
    def enabled(self) -> bool:
        env_allowed = self.env in self.config.allowed_envs and EnvironmentType.is_allowed(self.env)
        env_enabled = os.getenv("SELF_HEALING_ENABLED", "").lower() in ("1", "true", "yes")
        return env_allowed and (self.config.enabled or env_enabled)

    def locate(self, context: LocatorContext, *, timeout: int | None = None) -> HealingResult:
        timeout = timeout or self.config.timeout_ms
        key = context.description or context.selector or ",".join(context.selectors) or context.role or "unknown"
        if self._breaker and self._breaker.is_open(key):
            return HealingResult(None, False, "circuit_open", error="self-healing circuit breaker is open")
        if self.heal_count >= self.config.max_heals_per_page:
            return HealingResult(None, False, "heal_limit", error="self-healing page limit reached")

        for strategy in self.config.strategies[: self.config.max_attempts_per_action]:
            result = self._try_strategy(strategy, context, timeout)
            if result.locator is not None:
                if result.healed:
                    self.heal_count += 1
                if self._breaker:
                    self._breaker.record_success(key)
                return result

        if self._breaker:
            self._breaker.record_failure(key)
        return HealingResult(None, False, "not_found", error="no self-healing strategy matched")

    def execute(
        self,
        action: str,
        context: LocatorContext,
        operation: Callable[[Locator], None],
        *,
        timeout: int | None = None,
    ) -> bool:
        started = time.time()
        result = self.locate(context, timeout=timeout)
        if result.locator is None:
            self._record_event(action, context, result, started)
            return False
        try:
            operation(result.locator)
            if result.healed:
                self._attach_success(action, context, result)
                self._record_event(action, context, result, started)
            return True
        except Exception as exc:
            failed = HealingResult(
                None,
                result.healed,
                result.strategy,
                selector=result.selector,
                candidate_count=result.candidate_count,
                error=str(exc),
            )
            self._record_event(action, context, failed, started)
            return False

    def _try_strategy(self, strategy: str, context: LocatorContext, timeout: int) -> HealingResult:
        try:
            if strategy == "exact_selector" and context.selector:
                return self._candidate(self.page.locator(context.selector), strategy, context.selector, False, timeout)
            if strategy == "selector_chain":
                for selector in context.selectors:
                    result = self._candidate(
                        self.page.locator(selector),
                        strategy,
                        selector,
                        selector != context.selector,
                        timeout,
                    )
                    if result.locator is not None:
                        return result
            if strategy == "role_name" and context.role:
                for name in context.names:
                    result = self._candidate(
                        self.page.get_by_role(context.role, name=name),
                        strategy,
                        name,
                        True,
                        timeout,
                    )
                    if result.locator is not None:
                        return result
            if strategy == "text":
                for text in self._text_candidates(context):
                    result = self._candidate(self.page.get_by_text(text), strategy, text, True, timeout)
                    if result.locator is not None:
                        return result
            if strategy == "semantic_attr":
                for selector in self._semantic_selectors(context):
                    result = self._candidate(self.page.locator(selector), strategy, selector, True, timeout)
                    if result.locator is not None:
                        return result
            if strategy == "dom_text":
                selector = self._find_by_dom_text(context)
                if selector:
                    return self._candidate(self.page.locator(selector), strategy, selector, True, timeout)
        except Exception as exc:
            logger.debug("Self-healing strategy {} failed: {}", strategy, exc)
        return HealingResult(None, False, strategy)

    def _candidate(self, locator: Locator, strategy: str, selector: str, healed: bool, timeout: int) -> HealingResult:
        count = self._safe_count(locator)
        if count == 0:
            return HealingResult(
                None,
                healed,
                strategy,
                selector=selector,
                candidate_count=count,
                error="not found",
            )
        if self.config.strict_unique_match and count not in (None, 1):
            return HealingResult(
                None,
                healed,
                strategy,
                selector=selector,
                candidate_count=count,
                error="ambiguous match",
            )
        target = locator.first if count and count > 0 else locator
        target.wait_for(timeout=timeout)
        return HealingResult(target, healed, strategy, selector=selector, candidate_count=count)

    def _safe_count(self, locator: Locator) -> int | None:
        try:
            return locator.count()
        except Exception:
            return None

    def _text_candidates(self, context: LocatorContext) -> list[str]:
        values = [context.text, context.description, *context.names]
        candidates: list[str] = []
        for value in values:
            if value and value not in candidates:
                candidates.append(value)
                compact = re.sub(r"\s+", "", value)
                if compact and compact != value:
                    candidates.append(compact)
        return candidates

    def _semantic_selectors(self, context: LocatorContext) -> list[str]:
        selectors = []
        attrs = {**context.semantic_attrs}
        if context.description:
            attrs.setdefault("aria-label", context.description)
            attrs.setdefault("title", context.description)
            attrs.setdefault("placeholder", context.description)
        for name in context.names:
            attrs.setdefault("name", name)
        for attr, value in attrs.items():
            escaped = value.replace('"', '\\"')
            selectors.append(f'[{attr}="{escaped}"]')
            selectors.append(f'[{attr}*="{escaped}"]')
        return selectors

    def _find_by_dom_text(self, context: LocatorContext) -> str | None:
        texts = self._text_candidates(context)
        if not texts:
            return None
        return self.page.evaluate(
            """
            (texts) => {
                const candidates = Array.from(document.querySelectorAll(
                    'button,a,input,textarea,[role],[aria-label],[title],[placeholder]'
                ));
                const norm = (v) => String(v || '').replace(/\\s+/g, '');
                for (const text of texts) {
                    const target = norm(text);
                    for (let i = 0; i < candidates.length; i += 1) {
                        const el = candidates[i];
                        const haystack = norm([
                            el.innerText,
                            el.textContent,
                            el.getAttribute('aria-label'),
                            el.getAttribute('title'),
                            el.getAttribute('placeholder'),
                            el.getAttribute('value')
                        ].join(' '));
                        if (target && haystack.includes(target)) {
                            el.setAttribute('data-self-healing-match', `match-${Date.now()}-${i}`);
                            return `[data-self-healing-match="${el.getAttribute('data-self-healing-match')}"]`;
                        }
                    }
                }
                return null;
            }
            """,
            texts,
        )

    def _attach_success(self, action: str, context: LocatorContext, result: HealingResult) -> None:
        if not self.config.attach_allure:
            return
        payload = {
            "action": action,
            "strategy": result.strategy,
            "selector": result.selector,
            "original_selector": context.selector,
            "description": context.description,
            "candidate_count": result.candidate_count,
        }
        try:
            allure.attach(
                json.dumps(payload, ensure_ascii=False, indent=2),
                "self-healing-event",
                allure.attachment_type.JSON,
            )
            if self.config.screenshot_on_success:
                path = Path("reports/screenshots") / f"self_healing_{int(time.time() * 1000)}.png"
                path.parent.mkdir(parents=True, exist_ok=True)
                self.page.screenshot(path=str(path), full_page=True)
                allure.attach.file(
                    str(path),
                    name="self-healing-screenshot",
                    attachment_type=allure.attachment_type.PNG,
                )
        except Exception as exc:
            logger.debug("Failed to attach self-healing evidence: {}", exc)

    def _record_event(self, action: str, context: LocatorContext, result: HealingResult, started: float) -> None:
        if not self.config.metrics_enabled and not metrics_enabled():
            return
        event = {
            "type": "self_healing",
            "ts": time.time(),
            "action": action,
            "strategy": result.strategy,
            "healed": result.healed,
            "success": result.locator is not None,
            "selector": result.selector,
            "original_selector": context.selector,
            "description": context.description,
            "candidate_count": result.candidate_count,
            "duration_sec": round(time.time() - started, 4),
            "error": result.error,
            "url": getattr(self.page, "url", ""),
        }
        try:
            metrics_root = Path(self.config.metrics_root) if self.config.metrics_root else Path.cwd()
            HarnessMetricsRecorder(default_metrics_path(metrics_root)).write_event(event)
        except Exception as exc:
            logger.debug("Failed to record self-healing metric: {}", exc)


def load_self_healing_config(path: str | Path = "configs/self_healing.yaml") -> SelfHealingConfig:
    config_path = Path(path)
    if not config_path.exists():
        example_path = config_path.with_name("self_healing.example.yaml")
        if not example_path.exists():
            return SelfHealingConfig()
        config_path = example_path
    with config_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    breaker = raw.get("circuit_breaker", {}) or {}
    return SelfHealingConfig(
        enabled=bool(raw.get("enabled", False)),
        allowed_envs=list(raw.get("allowed_envs", ["test", "test_env", "uat"])),
        max_attempts_per_action=int(raw.get("max_attempts_per_action", 6)),
        max_heals_per_page=int(raw.get("max_heals_per_page", 20)),
        strict_unique_match=bool(raw.get("strict_unique_match", True)),
        attach_allure=bool(raw.get("attach_allure", True)),
        screenshot_on_success=bool(raw.get("screenshot_on_success", True)),
        metrics_enabled=bool(raw.get("metrics_enabled", True)),
        timeout_ms=int(raw.get("timeout_ms", 10000)),
        strategies=list(raw.get("strategies", DEFAULT_STRATEGIES)),
        failure_threshold=int(breaker.get("failure_threshold", 5)),
        cooldown_seconds=int(breaker.get("cooldown_seconds", 300)),
        metrics_root=raw.get("metrics_root"),
    )

"""Backward-compatible environment facade.

The canonical configuration and endpoint validation live in
``modules.auto_test.core.config_manager``.  This module keeps the historical
``Environment`` API for existing callers while sourcing its configuration and
security policy from that canonical implementation.
"""

import copy
import os
from dataclasses import dataclass
from typing import Any

from modules.auto_test.core.config_manager import (
    EnvironmentSecurityError,
    EnvironmentType,
    get_config,
    validate_environment as _validate_canonical_environment,
)

__all__ = [
    "APIConfig",
    "BrowserConfig",
    "EndpointConfig",
    "Environment",
    "EnvironmentSecurityError",
    "EnvironmentType",
    "get_environment",
    "validate_environment",
]


@dataclass
class EndpointConfig:
    base_url: str
    api_base_url: str
    auth_url: str
    admin_path: str = "/oms-admin"


@dataclass
class BrowserConfig:
    headless: bool = True
    browser: str = "chromium"
    slow_mo: int = 0
    viewport_width: int = 1920
    viewport_height: int = 1080
    video: str = "off"
    trace: str = "off"


@dataclass
class APIConfig:
    timeout: int = 30
    retries: int = 3
    verify_ssl: bool = True


class Environment:
    _instance: "Environment | None" = None
    _config: dict[str, Any] = {}

    def __new__(cls, env: str | None = None) -> "Environment":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_environment(env or os.getenv("TEST_ENV", "test"))
        return cls._instance

    def _load_environment(self, env: str) -> None:
        self._validate_environment(env)
        self._env_name = env
        self._load_config(env)
        self._load_endpoints(env)

    def _validate_environment(self, env: str) -> None:
        _validate_canonical_environment(env)

    def _load_config(self, env: str) -> None:
        # Reuse the canonical loader so legacy callers cannot select a
        # different config path or bypass endpoint validation.
        self._canonical_config = get_config(env)
        self._config = self._canonical_config.config
        self._config["env"] = env

    def _resolve_env_vars(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._resolve_env_vars(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_env_vars(item) for item in obj]
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            env_var = obj[2:-1]
            default = ""
            if ":-" in env_var:
                env_var, default = env_var.split(":-", 1)
            return os.getenv(env_var, default)
        return obj

    def _load_endpoints(self, env: str) -> None:
        # ConfigManager owns endpoint normalization and authentication-path
        # validation.  Keep the legacy dataclass shape, but never rebuild
        # URLs from the removed origin/ui_path/api_path fields here.
        canonical_config = getattr(self, "_canonical_config", None)
        if canonical_config is None or canonical_config.env != env:
            canonical_config = get_config(env)
            self._canonical_config = canonical_config
        endpoints = canonical_config.endpoints

        self.endpoints = EndpointConfig(
            base_url=endpoints.base_url,
            api_base_url=endpoints.api_base_url,
            auth_url=endpoints.auth_url,
            admin_path=endpoints.admin_path,
        )

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        keys = key.split(".")
        target = self._config
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value

    @property
    def config(self) -> dict[str, Any]:
        return copy.deepcopy(self._config)

    @property
    def name(self) -> str:
        return self._env_name

    @property
    def is_test(self) -> bool:
        return self._env_name == "test"

    @property
    def is_uat(self) -> bool:
        return self._env_name == "uat"

    @property
    def browser_config(self) -> BrowserConfig:
        pw = self._config.get("playwright", {})
        return BrowserConfig(
            headless=pw.get("headless", True),
            browser=pw.get("browser", "chromium"),
            slow_mo=pw.get("slow_mo", 0),
            viewport_width=pw.get("viewport", {}).get("width", 1920),
            viewport_height=pw.get("viewport", {}).get("height", 1080),
            video=pw.get("video", "off"),
            trace=pw.get("trace", "off"),
        )

    @property
    def api_config(self) -> APIConfig:
        api = self._config.get("api", {})
        return APIConfig(
            timeout=api.get("timeout", 30), retries=api.get("retries", 3), verify_ssl=api.get("verify_ssl", True)
        )

    @classmethod
    def reset(cls) -> None:
        cls._instance = None


def get_environment(env: str | None = None) -> Environment:
    if env:
        Environment.reset()
    return Environment(env)


def validate_environment(env: str) -> None:
    """Validate the environment using the canonical configuration policy."""
    _validate_canonical_environment(env)

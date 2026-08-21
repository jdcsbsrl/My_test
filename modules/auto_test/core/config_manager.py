import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml
from dotenv import load_dotenv

load_dotenv()


class EnvironmentType(Enum):
    TEST = "test"
    TEST_ENV = "test_env"
    UAT = "uat"
    PRODUCTION = "production"

    @classmethod
    def is_allowed(cls, env: str) -> bool:
        return env.lower() in [cls.TEST.value, cls.TEST_ENV.value, cls.UAT.value]

    @classmethod
    def is_production(cls, env: str) -> bool:
        return env.lower() == cls.PRODUCTION.value


class EnvironmentSecurityError(Exception):
    pass


_DEFAULT_ALLOWED_ORIGINS = {
    "test": frozenset({"https://erptest.dayoneerp.com"}),
    "test_env": frozenset({"https://erptest.dayoneerp.com"}),
    "uat": frozenset({"https://erpuat.dayoneerp.com"}),
}


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


class ConfigManager:
    _instance: "ConfigManager | None" = None

    def __new__(cls, env: str | None = None) -> "ConfigManager":
        target_env = str(env or os.getenv("TEST_ENV", "test")).strip().lower()
        if cls._instance is None or cls._instance.env != target_env:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
            cls._instance._config: dict[str, Any] = {}
            cls._instance._env_name = target_env
            cls._instance._load_config(target_env)
        return cls._instance

    def _load_config(self, env: str) -> None:
        self._validate_environment(env)

        config_path = Path(__file__).resolve().parents[3] / "configs" / f"{env}.yaml"
        if not config_path.exists():
            raw_config = self._build_environment_config(env)
        else:
            with open(config_path, encoding="utf-8") as f:
                raw_config = yaml.safe_load(f)

        if raw_config is None:
            raise ValueError(f"Config file is empty: {config_path}")

        env_config = raw_config.get(env, raw_config)
        self._config = self._resolve_env_vars(env_config)
        self._config["env"] = env

        self._validate_loaded_config()

        self._load_endpoints()

    def _validate_loaded_config(self) -> None:
        """Validate resolved configuration before any client is created."""
        origin = str(self._config.get("origin", "")).strip()
        if not origin:
            for candidate in (
                self._config.get("base_url"),
                self._config.get("api_base_url"),
                self._config.get("api", {}).get("base_url")
                if isinstance(self._config.get("api", {}), dict)
                else None,
            ):
                if candidate:
                    origin = self._origin_from_url(str(candidate))
                    break
        if not origin:
            raise ValueError(
                f"Missing test environment origin for '{self.env}'. "
                "Set the environment YAML or the corresponding *_WEB_API_BASE_URL variable."
            )
        origin = self._normalize_origin(origin, field="origin")
        if origin not in self._allowed_origins():
            raise EnvironmentSecurityError(
                f"Refusing to run automation against an unapproved endpoint for {self.env}: {origin}. "
                "Add the exact origin to the environment-specific allowlist if this is an approved test stack."
            )

        ui_path = str(self._config.get("ui_path", ""))
        api_path = str(self._config.get("api_path", "/oms-uat-api"))
        ui_url = str(self._config.get("base_url") or f"{origin}{ui_path}").strip()
        api_url = str(
            self._config.get("api_base_url")
            or (
                self._config.get("api", {}).get("base_url")
                if isinstance(self._config.get("api", {}), dict)
                else None
            )
            or f"{origin}{api_path}"
        ).strip()
        self._validate_same_origin(ui_url, origin, "base_url")
        self._validate_same_origin(api_url, origin, "api_base_url")
        self._config["origin"] = origin
        self._config["base_url"] = ui_url.rstrip("/")
        self._config["api_base_url"] = api_url.rstrip("/")
        if not isinstance(self._config.get("api"), dict):
            self._config["api"] = {}
        self._config["api"]["base_url"] = api_url.rstrip("/")

    @staticmethod
    def _build_environment_config(env: str) -> dict[str, Any]:
        """Build a secrets-free CI configuration when private YAML is not checked in."""
        prefix = "UAT" if env == "uat" else "TEST"
        api_value = os.getenv(f"{prefix}_WEB_API_BASE_URL", "").strip()
        default_ui_path = "/oms-uat-ui" if env == "uat" else "/oms-ui"
        default_api_path = "/oms-uat-api" if env == "uat" else "/oms-api"
        parsed_api = urlparse(api_value)
        origin = ConfigManager._origin_from_url(api_value)
        if api_value and not origin:
            # Preserve the invalid value so the normal validator can return a
            # safe, consistent configuration error without silently falling
            # back to another endpoint.
            origin = api_value
        if origin and parsed_api.path not in {"", "/"} and not parsed_api.query and not parsed_api.fragment:
            api_base_url = api_value.rstrip("/")
        else:
            api_base_url = f"{origin}{default_api_path}"
        return {
            "origin": origin,
            "ui_path": default_ui_path,
            "api_path": default_api_path,
            "base_url": os.getenv(f"{prefix}_WEB_BASE_URL") or f"{origin}{default_ui_path}",
            "api_base_url": api_base_url,
            "api": {
                "base_url": api_base_url,
                "timeout": 30,
                "retries": 3,
                "verify_ssl": True,
            },
            "playwright": {
                "headless": True,
                "browser": "chromium",
                "slow_mo": 0,
                "viewport": {"width": 1920, "height": 1080},
                "video": "off",
                "trace": "off",
            },
        }

    def _validate_environment(self, env: str) -> None:
        if not EnvironmentType.is_allowed(env):
            raise EnvironmentSecurityError(
                f"环境安全异常: 禁止在生产环境 (production) 执行自动化测试。\n"
                f"当前环境: {env}\n"
                f"允许的环境: test, test_env, uat\n"
                f"如需执行测试，请联系项目负责人获取授权。"
            )

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

    def _load_endpoints(self) -> None:
        api_base_url = self._config["api_base_url"]
        login_path = str(self.get("api.auth_login_path", "/oms-admin/auth/login")).strip()
        if not login_path.startswith("/") or ".." in login_path.split("/") or "\\" in login_path:
            raise EnvironmentSecurityError("Configured authentication path is unsafe")

        self._endpoints = EndpointConfig(
            base_url=self._config["base_url"],
            api_base_url=api_base_url,
            auth_url=f"{api_base_url.rstrip('/')}{login_path}",
            admin_path="/oms-admin",
        )

    @staticmethod
    def _origin_from_url(value: str) -> str:
        parsed = urlparse(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""
        return f"{parsed.scheme}://{parsed.netloc}".rstrip("/").lower()

    @classmethod
    def _normalize_origin(cls, value: str, *, field: str = "endpoint") -> str:
        origin = cls._origin_from_url(value)
        parsed = urlparse(value.strip())
        if not origin or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError(f"Invalid {field}: expected an HTTP(S) origin without path, query, fragment, or credentials")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise EnvironmentSecurityError(f"HTTPS is required for non-local {field}")
        return origin

    def _allowed_origins(self) -> set[str]:
        allowed = set(_DEFAULT_ALLOWED_ORIGINS.get(self._env_name.lower(), ()))
        configured = self._config.get("allowed_origins", [])
        if isinstance(configured, str):
            configured = configured.split(",")
        for value in configured or []:
            allowed.add(self._normalize_origin(str(value), field="allowed origin"))
        for env_key in (f"{self._env_name.upper()}_ALLOWED_ORIGINS", "AUTO_TEST_ALLOWED_ORIGINS"):
            raw = os.getenv(env_key, "")
            if raw:
                for value in raw.split(","):
                    allowed.add(self._normalize_origin(value, field=env_key))
        return allowed

    def _allowed_external_origins(self) -> set[str]:
        allowed: set[str] = set()
        configured = self._config.get("allowed_external_origins", [])
        if isinstance(configured, str):
            configured = configured.split(",")
        for value in configured or []:
            allowed.add(self._normalize_origin(str(value), field="allowed external origin"))
        for env_key in ("OPENAPI_ALLOWED_ORIGINS", "AUTO_TEST_ALLOWED_EXTERNAL_ORIGINS"):
            raw = os.getenv(env_key, "")
            if raw:
                for value in raw.split(","):
                    allowed.add(self._normalize_origin(value, field=env_key))
        return allowed

    def _validate_same_origin(self, endpoint: str, origin: str, field: str) -> None:
        parsed = urlparse(endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or "\\" in parsed.path
            or ".." in parsed.path.split("/")
        ):
            raise ValueError(f"Invalid {field}: credentials, query strings and fragments are not allowed")
        if self._origin_from_url(endpoint) != origin:
            raise EnvironmentSecurityError(f"{field} must use the approved environment origin: {endpoint!r}")

    def validate_endpoint(self, endpoint: str, *, purpose: str = "api", allow_external: bool = True) -> str:
        """Validate an absolute endpoint before a request or browser navigation."""
        value = str(endpoint or "").strip()
        if not value:
            raise ValueError(f"Empty {purpose} endpoint")
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise EnvironmentSecurityError(f"Invalid absolute {purpose} endpoint: {value!r}")
        origin = self._origin_from_url(value)
        allowed = {self._config["origin"]}
        if allow_external:
            allowed.update(self._allowed_external_origins())
        if origin not in allowed:
            raise EnvironmentSecurityError(f"Unapproved {purpose} endpoint: {value!r}")
        if parsed.username or parsed.password or parsed.fragment:
            raise EnvironmentSecurityError(f"Credentials and fragments are not allowed in {purpose} endpoints")
        if "\\" in parsed.path or ".." in parsed.path.split("/"):
            raise EnvironmentSecurityError(f"Traversal is not allowed in {purpose} endpoints")
        if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise EnvironmentSecurityError(f"HTTPS is required for {purpose} endpoints")
        return value

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
        return self._config.copy()

    @property
    def env(self) -> str:
        return str(self._config.get("env", "test"))

    @property
    def name(self) -> str:
        return self._env_name

    @property
    def base_url(self) -> str:
        return str(self._config.get("base_url", ""))

    @property
    def api_base_url(self) -> str:
        return str(self.get("api.base_url", self._config.get("api_base_url", "")))

    @property
    def endpoints(self) -> EndpointConfig:
        return self._endpoints

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

    @property
    def is_test(self) -> bool:
        return self._env_name == "test"

    @property
    def is_uat(self) -> bool:
        return self._env_name == "uat"

    @classmethod
    def reset(cls) -> None:
        cls._instance = None


def get_config(env: str | None = None) -> ConfigManager:
    if env:
        ConfigManager.reset()
    return ConfigManager(env)


def validate_environment(env: str) -> None:
    if not EnvironmentType.is_allowed(env):
        raise EnvironmentSecurityError(
            f"环境安全异常: 禁止在生产环境 (production) 执行自动化测试。\n"
            f"当前环境: {env}\n"
            f"允许的环境: test, test_env, uat\n"
            f"如需执行测试，请联系项目负责人获取授权。"
        )


def get_environment(env: str | None = None) -> ConfigManager:
    return get_config(env)

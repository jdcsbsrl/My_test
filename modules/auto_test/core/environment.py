import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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
        if not EnvironmentType.is_allowed(env):
            raise EnvironmentSecurityError(
                f"环境安全异常: 禁止在生产环境 (production) 执行自动化测试。\n"
                f"当前环境: {env}\n"
                f"允许的环境: test, uat\n"
                f"如需执行测试，请联系项目负责人获取授权。"
            )

    def _load_config(self, env: str) -> None:
        config_path = Path(__file__).parent.parent / "configs" / f"{env}.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        self._config = self._resolve_env_vars(self._config)
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
        origin = self._config.get("origin", os.getenv("TEST_WEB_API_BASE_URL"))
        ui_path = self._config.get("ui_path", "")
        api_path = self._config.get("api_path", "/oms-uat-api")

        self.endpoints = EndpointConfig(
            base_url=f"{origin}{ui_path}",
            api_base_url=f"{origin}{api_path}",
            auth_url=f"{origin}{api_path}/oms-admin/auth/login",
            admin_path="/oms-admin",
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
        return self._config.copy()

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
    if not EnvironmentType.is_allowed(env):
        raise EnvironmentSecurityError(
            f"环境安全异常: 禁止在生产环境 (production) 执行自动化测试。\n"
            f"当前环境: {env}\n"
            f"允许的环境: test, uat\n"
            f"如需执行测试，请联系项目负责人获取授权。"
        )

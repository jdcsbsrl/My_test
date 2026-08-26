from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from functools import wraps
from typing import Any
from urllib.parse import urlparse

import yaml

from modules.auto_test.core.config_manager import EnvironmentSecurityError, EnvironmentType
from modules.auto_test.core.secret_provider import get_secret, runtime_environment

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_PRODUCTION_MARKERS = ("production", "/prod", "prod.", "_prod")


def _load_redis_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "configs", "redis.yaml")
    config_path = os.path.abspath(config_path)
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            raise EnvironmentSecurityError("Invalid Redis configuration") from None
        if not isinstance(data, Mapping):
            raise EnvironmentSecurityError("Invalid Redis configuration")
        config = data.get("redis", {})
        if not isinstance(config, Mapping):
            raise EnvironmentSecurityError("Invalid Redis configuration")
        environment = _runtime_environment()
        scoped = config.get(environment)
        if isinstance(scoped, Mapping):
            return dict(scoped)
        return dict(config)
    return {}


_redis_client: Any = None


def _runtime_environment() -> str:
    return runtime_environment()


def _validate_environment(configured_environment: object = None) -> str:
    environment = _runtime_environment()
    if not EnvironmentType.is_allowed(environment):
        raise EnvironmentSecurityError(
            f"Redis access is disabled for environment {environment!r}; " "only test, test_env and uat are allowed."
        )
    if configured_environment is not None and str(configured_environment).strip().lower() != environment:
        raise EnvironmentSecurityError("Redis environment binding mismatch")
    return environment


def _allowed_hosts() -> set[str]:
    allowed = set(_LOCAL_HOSTS)
    raw_allowed_hosts = get_secret("AUTO_TEST_ALLOWED_REDIS_HOSTS") or ""
    allowed.update(host.strip().lower() for host in raw_allowed_hosts.split(",") if host.strip())
    return allowed


def _validate_host(host: object, database: object = "") -> str:
    normalized_host = str(host or "").strip().lower().strip("[]")
    target = f"{normalized_host}/{str(database or '').lower()}"
    if any(marker in target for marker in _PRODUCTION_MARKERS):
        raise EnvironmentSecurityError("Refusing Redis connection to a production-looking target")
    if normalized_host not in _allowed_hosts():
        raise EnvironmentSecurityError(f"Refusing Redis connection to unapproved host {normalized_host!r}")
    return normalized_host


def _secret_from_environment(environment: str, name: str, *fallbacks: str) -> str:
    prefix = "UAT" if environment == "uat" else "TEST"
    for key in (f"{prefix}_{name}", *fallbacks):
        value = get_secret(name, environment=environment, fallbacks=(key,))
        if value:
            return value
    return ""


def _redis_connection_settings(cfg: dict) -> tuple[str, int, str, int]:
    environment = _validate_environment(cfg.get("environment", cfg.get("env")))
    raw_url = _secret_from_environment(environment, "REDIS_URL", "REDIS_URL") or cfg.get("url")
    try:
        if raw_url:
            parsed = urlparse(str(raw_url))
            if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
                raise ValueError
            host = parsed.hostname
            port = parsed.port or 6379
            db_num = int(parsed.path.lstrip("/") or cfg.get("db", 0))
            url_password = parsed.password or ""
        else:
            host = str(cfg.get("host", "localhost"))
            port = int(cfg.get("port", 6379))
            db_num = int(cfg.get("db", 0))
            url_password = ""

        _validate_host(host, db_num)
        password = _secret_from_environment(environment, "REDIS_PASSWORD", "REDIS_PASSWORD")
        if not password:
            password = url_password or cfg.get("password", "")
        password = os.path.expandvars(str(password))
        if password.startswith("${") and password.endswith("}"):
            password = ""
        return str(host), port, password, db_num
    except EnvironmentSecurityError:
        raise
    except Exception:
        raise EnvironmentSecurityError("Invalid Redis connection configuration") from None


def _get_client() -> Any:
    global _redis_client
    _validate_environment()
    if _redis_client is not None:
        return _redis_client

    cfg = _load_redis_config()
    host, port, password, db_num = _redis_connection_settings(cfg)
    try:
        import redis as _redis_mod
    except ImportError:
        return None

    try:
        pool = _redis_mod.ConnectionPool(
            host=host,
            port=port,
            password=password if password else None,
            db=db_num,
            decode_responses=True,
            max_connections=10,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        _redis_client = _redis_mod.Redis(connection_pool=pool)
    except Exception:
        raise EnvironmentSecurityError("Redis client initialization failed") from None
    return _redis_client


def _try_client() -> Any:
    try:
        return _get_client()
    except EnvironmentSecurityError:
        raise
    except Exception:
        return None


def suppress_redis_errors(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except EnvironmentSecurityError:
            raise
        except Exception:
            return None

    return wrapper


@suppress_redis_errors
def get_cached(key: str) -> Any | None:
    client = _try_client()
    if client is None:
        return None
    value = client.get(key)
    if value is not None:
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return None


@suppress_redis_errors
def set_cached(key: str, value: Any, ttl: int = 3600) -> bool:
    client = _try_client()
    if client is None:
        return False
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, default=str)
    client.set(key, value, ex=ttl)
    return True


@suppress_redis_errors
def delete_key(key: str) -> bool:
    client = _try_client()
    if client is None:
        return False
    client.delete(key)
    return True


@suppress_redis_errors
def delete_pattern(pattern: str) -> int:
    client = _try_client()
    if client is None:
        return 0
    count = 0
    for key in client.scan_iter(match=pattern):
        client.delete(key)
        count += 1
    return count


@suppress_redis_errors
def flush_cache() -> bool:
    client = _try_client()
    if client is None:
        return False
    client.flushdb()
    return True


def reset_client() -> None:
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:
            pass
        _redis_client = None

from __future__ import annotations

import json
import os
from collections.abc import Callable
from functools import wraps
from typing import Any

import yaml


def _load_redis_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "configs", "redis.yaml")
    config_path = os.path.abspath(config_path)
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("redis", {})
    return {}


_redis_client: Any = None


def _get_client() -> Any:
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis as _redis_mod
    except ImportError:
        return None

    cfg = _load_redis_config()
    host = cfg.get("host", "localhost")
    port = int(cfg.get("port", 6379))
    password = os.getenv("REDIS_PASSWORD") or cfg.get("password", "")
    password = os.path.expandvars(str(password))
    db_num = int(cfg.get("db", 0))

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
    return _redis_client


def _try_client() -> Any:
    try:
        return _get_client()
    except Exception:
        return None


def suppress_redis_errors(func: Callable) -> Callable:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
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
    client.setex(key, ttl, value)
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

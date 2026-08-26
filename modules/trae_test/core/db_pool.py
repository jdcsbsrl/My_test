from __future__ import annotations

import os
from collections.abc import Mapping

import yaml
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session, sessionmaker

from modules.auto_test.core.config_manager import EnvironmentSecurityError, EnvironmentType
from modules.auto_test.core.secret_provider import get_secret, runtime_environment

_engine: Engine | None = None
_session_factory: sessionmaker | None = None

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 5
DB_POOL_RECYCLE = 600
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_PRODUCTION_MARKERS = ("production", "/prod", "prod.", "_prod")


def _load_db_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "configs", "database.yaml")
    config_path = os.path.abspath(config_path)
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            raise EnvironmentSecurityError("Invalid database configuration") from None
        if not isinstance(data, Mapping):
            raise EnvironmentSecurityError("Invalid database configuration")
        config = data.get("database", {})
        if not isinstance(config, Mapping):
            raise EnvironmentSecurityError("Invalid database configuration")
        environment = _runtime_environment()
        scoped = config.get(environment)
        if isinstance(scoped, Mapping):
            return dict(scoped)
        return dict(config)
    return {}


def _runtime_environment() -> str:
    return runtime_environment()


def _validate_environment(configured_environment: object = None) -> str:
    environment = _runtime_environment()
    if not EnvironmentType.is_allowed(environment):
        raise EnvironmentSecurityError(
            f"Database access is disabled for environment {environment!r}; " "only test, test_env and uat are allowed."
        )
    if configured_environment is not None and str(configured_environment).strip().lower() != environment:
        raise EnvironmentSecurityError("Database environment binding mismatch")
    return environment


def _allowed_hosts() -> set[str]:
    allowed = set(_LOCAL_HOSTS)
    raw_allowed_hosts = get_secret("AUTO_TEST_ALLOWED_DB_HOSTS") or ""
    allowed.update(host.strip().lower() for host in raw_allowed_hosts.split(",") if host.strip())
    return allowed


def _validate_host(host: object, database: object = "") -> str:
    normalized_host = str(host or "").strip().lower().strip("[]")
    target = f"{normalized_host}/{str(database or '').lower()}"
    if any(marker in target for marker in _PRODUCTION_MARKERS):
        raise EnvironmentSecurityError("Refusing database connection to a production-looking target")
    if normalized_host not in _allowed_hosts():
        raise EnvironmentSecurityError(f"Refusing database connection to unapproved host {normalized_host!r}")
    return normalized_host


def _secret_from_environment(environment: str, name: str, *fallbacks: str) -> str:
    prefix = "UAT" if environment == "uat" else "TEST"
    for key in (f"{prefix}_{name}", *fallbacks):
        value = get_secret(name, environment=environment, fallbacks=(key,))
        if value:
            return value
    return ""


def _build_url(cfg: dict) -> URL:
    environment = _validate_environment(cfg.get("environment", cfg.get("env")))
    raw_url = _secret_from_environment(environment, "DATABASE_URL", "DATABASE_URL") or cfg.get("url")
    try:
        if raw_url:
            url = make_url(str(raw_url))
            host = url.host or "localhost"
            _validate_host(host, url.database)
            return url

        host = cfg.get("host", "localhost")
        port = int(cfg.get("port", 5432))
        name = str(cfg.get("name", "test_erp_kb"))
        user = str(cfg.get("user", "postgres"))
        password = _secret_from_environment(environment, "DB_PASSWORD", "DB_PASSWORD") or cfg.get("password", "")
        password = os.path.expandvars(str(password))
        _validate_host(host, name)
        return URL.create(
            "postgresql",
            username=user,
            password=password,
            host=str(host),
            port=port,
            database=name,
        )
    except EnvironmentSecurityError:
        raise
    except Exception:
        raise EnvironmentSecurityError("Invalid database connection configuration") from None


def get_engine() -> Engine:
    global _engine, _session_factory
    _validate_environment()
    if _engine is None:
        cfg = _load_db_config()
        url = _build_url(cfg)
        try:
            _engine = create_engine(
                url,
                pool_size=DB_POOL_SIZE,
                max_overflow=DB_MAX_OVERFLOW,
                pool_recycle=DB_POOL_RECYCLE,
                pool_pre_ping=True,
            )
        except Exception:
            raise EnvironmentSecurityError("Database engine initialization failed") from None
        _session_factory = sessionmaker(bind=_engine)
    return _engine


def get_session() -> Session:
    engine = get_engine()
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=engine)
    return _session_factory()


def close_pool() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
        _engine = None
        _session_factory = None

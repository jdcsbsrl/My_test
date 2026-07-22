from __future__ import annotations

import os

import yaml
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker | None = None

DB_POOL_SIZE = 5
DB_MAX_OVERFLOW = 5
DB_POOL_RECYCLE = 600


def _load_db_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "configs", "database.yaml")
    config_path = os.path.abspath(config_path)
    if os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("database", {})
    return {}


def _build_url(cfg: dict) -> str:
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 5432)
    name = cfg.get("name", "test_erp_kb")
    user = cfg.get("user", "postgres")
    password = os.getenv("DB_PASSWORD") or cfg.get("password", "")
    password = os.path.expandvars(str(password))
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


def get_engine() -> Engine:
    global _engine, _session_factory
    if _engine is None:
        cfg = _load_db_config()
        url = os.getenv("DATABASE_URL") or _build_url(cfg)
        _engine = create_engine(
            url,
            pool_size=DB_POOL_SIZE,
            max_overflow=DB_MAX_OVERFLOW,
            pool_recycle=DB_POOL_RECYCLE,
            pool_pre_ping=True,
        )
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

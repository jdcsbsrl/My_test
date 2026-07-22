from __future__ import annotations

from modules.trae_test.core.db_pool import get_engine
from modules.trae_test.core.migration.schema import Base


def create_all_tables() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine, checkfirst=True)

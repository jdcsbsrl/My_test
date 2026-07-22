from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from modules.auto_test.core.config_manager import get_config
from modules.auto_test.core.logger import get_logger

logger = get_logger()


class DBHelper:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        database: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ) -> None:
        config = get_config()
        self.host = host or config.get("database.host", "localhost")
        self.port = port or config.get("database.port", 5432)
        self.database = database or config.get("database.name", "")
        self.user = user or config.get("database.user", "")
        self.password = password or config.get("database.password", "")
        self.connection = None
        self.cursor = None

    def connect(self) -> "DBHelper":
        self.connection = psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            cursor_factory=RealDictCursor,
        )
        self.cursor = self.connection.cursor()
        logger.info(f"Connected to database: {self.database}@{self.host}:{self.port}")
        return self

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if not self.cursor:
            raise RuntimeError("Database not connected. Call connect() first.")
        self.cursor.execute(sql, params)
        if self.cursor.description:
            return self.cursor.fetchall()
        self.connection.commit()
        return []

    def execute_many(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        if not self.cursor:
            raise RuntimeError("Database not connected. Call connect() first.")
        self.cursor.executemany(sql, params_list)
        self.connection.commit()

    def close(self) -> None:
        if self.cursor:
            self.cursor.close()
        if self.connection:
            self.connection.close()
            logger.info("Database connection closed")

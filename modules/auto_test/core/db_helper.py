import os
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from modules.auto_test.core.config_manager import EnvironmentSecurityError, EnvironmentType, get_config
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
        *,
        env: str | None = None,
    ) -> None:
        config = get_config(env) if env else get_config()
        requested_environment = EnvironmentType.normalize(env) if env is not None else ""
        configured_environment = EnvironmentType.normalize(getattr(config, "env", os.getenv("TEST_ENV", "test")))
        if requested_environment and requested_environment != configured_environment:
            raise EnvironmentSecurityError(
                f"Database environment mismatch: requested={requested_environment!r}, "
                f"configured={configured_environment!r}"
            )
        self.environment = requested_environment or configured_environment
        if not EnvironmentType.is_allowed(self.environment):
            raise EnvironmentSecurityError(
                f"Database access is disabled for environment {self.environment!r}; "
                "only test, test_env and uat are allowed."
            )
        prefix = "UAT" if self.environment == "uat" else "TEST"

        def configured(name: str, default: Any) -> Any:
            return (
                os.getenv(f"{prefix}_DB_{name.upper()}")
                or os.getenv(f"{prefix}_DATABASE_{name.upper()}")
                or config.get(f"database.{name}", default)
            )

        configured_values = {
            "host": configured("host", "localhost"),
            "port": configured("port", 5432),
            "name": configured("name", ""),
            "user": configured("user", ""),
            "password": configured("password", ""),
        }
        supplied_values = {"host": host, "port": port, "name": database, "user": user, "password": password}
        for name, value in supplied_values.items():
            if (
                value is not None
                and configured_values[name] not in (None, "")
                and str(value) != str(configured_values[name])
            ):
                raise EnvironmentSecurityError(
                    f"Explicit database {name} does not match the configured {self.environment} database"
                )
            if value is not None and configured_values[name] in (None, ""):
                configured_values[name] = value
        self.host = str(configured_values["host"])
        try:
            self.port = int(configured_values["port"])
        except (TypeError, ValueError) as exc:
            raise EnvironmentSecurityError("Database port must be an integer") from exc
        if not 1 <= self.port <= 65535:
            raise EnvironmentSecurityError("Database port must be between 1 and 65535")
        self.database = str(configured_values["name"])
        self.user = str(configured_values["user"])
        self.password = str(configured_values["password"])
        configured_env = (
            config.get("database.environment")
            or os.getenv(f"{prefix}_DB_ENV")
            or os.getenv("DB_ENV")
            or self.environment
        )
        self.database_environment = EnvironmentType.normalize(configured_env)
        self.connection = None
        self.cursor = None

    def _validate_target(self) -> None:
        if self.database_environment != self.environment:
            raise EnvironmentSecurityError(
                f"Database environment binding mismatch: configured={self.database_environment!r}, "
                f"runtime={self.environment!r}"
            )
        if not self.host:
            raise EnvironmentSecurityError("Database host must be configured before connecting")
        if not self.database:
            raise EnvironmentSecurityError("Database name must be configured before connecting")
        target = f"{self.host}/{self.database}".lower()
        if any(marker in target for marker in ("production", "/prod", "prod.", "_prod")):
            raise EnvironmentSecurityError("Refusing database connection to a production-looking target")
        allowed_hosts = {"localhost", "127.0.0.1", "::1"}
        raw_allowed_hosts = os.getenv("AUTO_TEST_ALLOWED_DB_HOSTS", "")
        allowed_hosts.update(host.strip().lower() for host in raw_allowed_hosts.split(",") if host.strip())
        if str(self.host).lower() not in allowed_hosts:
            raise EnvironmentSecurityError(
                f"Refusing database connection to unapproved host {self.host!r}; "
                "configure AUTO_TEST_ALLOWED_DB_HOSTS explicitly for an approved test database."
            )

    def connect(self) -> "DBHelper":
        self._validate_target()
        self.close()
        try:
            self.connection = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                cursor_factory=RealDictCursor,
            )
            self.cursor = self.connection.cursor()
        except Exception:
            self.close()
            raise
        logger.info(f"Connected to database: {self.database}@{self.host}:{self.port}")
        return self

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        if not self.cursor:
            raise RuntimeError("Database not connected. Call connect() first.")
        try:
            self.cursor.execute(sql, params)
            if self.cursor.description:
                return self.cursor.fetchall()
            self.connection.commit()
            return []
        except Exception:
            if self.connection:
                self.connection.rollback()
            raise

    def execute_many(self, sql: str, params_list: list[tuple[Any, ...]]) -> None:
        if not self.cursor:
            raise RuntimeError("Database not connected. Call connect() first.")
        try:
            self.cursor.executemany(sql, params_list)
            self.connection.commit()
        except Exception:
            if self.connection:
                self.connection.rollback()
            raise

    def close(self) -> None:
        cursor, connection = self.cursor, self.connection
        self.cursor = None
        self.connection = None
        if cursor:
            try:
                cursor.close()
            except Exception:
                logger.exception("Failed to close database cursor")
        if connection:
            try:
                connection.close()
                logger.info("Database connection closed")
            except Exception:
                logger.exception("Failed to close database connection")

    def __enter__(self) -> "DBHelper":
        return self.connect()

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

from __future__ import annotations

import psycopg

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class PostgresClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("shared.postgres.client")
        self._connection: psycopg.Connection | None = None

    def connect(self) -> None:
        if not self._settings.postgres_enabled:
            self._logger.info(
                "postgres_disabled",
                dsn=self._settings.postgres_dsn,
            )
            return

        self._connection = psycopg.connect(self._settings.postgres_dsn)
        self._connection.autocommit = True

        self._logger.info(
            "postgres_connected",
            dsn=self._settings.postgres_dsn,
        )

    def execute(self, query: str, params: tuple | None = None) -> None:
        if not self._settings.postgres_enabled:
            self._logger.info(
                "postgres_execute_skipped",
                reason="postgres_disabled",
            )
            return

        if self._connection is None:
            raise RuntimeError("Postgres client is not connected")

        with self._connection.cursor() as cursor:
            cursor.execute(query, params)

    def fetch_one(self, query: str, params: tuple | None = None) -> tuple | None:
        if not self._settings.postgres_enabled:
            self._logger.info(
                "postgres_fetch_skipped",
                reason="postgres_disabled",
            )
            return None

        if self._connection is None:
            raise RuntimeError("Postgres client is not connected")

        with self._connection.cursor() as cursor:
            cursor.execute(query, params)
            return cursor.fetchone()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None
from __future__ import annotations

from shared.logging.logger import get_logger
from shared.models import IndicatorEvent
from shared.postgres.client import PostgresClient


class IndicatorRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client
        self._logger = get_logger("indicator_engine.repository")

    def ensure_table(self) -> None:
        self._postgres_client.execute(
            """
            CREATE TABLE IF NOT EXISTS indicators_1m (
                id BIGSERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                bar_start_time TIMESTAMPTZ NOT NULL,
                ema_7 NUMERIC(18, 6) NOT NULL,
                ema_9 NUMERIC(18, 6) NOT NULL,
                sma_3 NUMERIC(18, 6) NOT NULL,
                sma_5 NUMERIC(18, 6) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(symbol, timeframe, bar_start_time)
            )
            """
        )
        self._logger.info(
            "indicator_table_ready",
            table="indicators_1m",
        )

    def upsert_indicator(self, event: IndicatorEvent) -> None:
        self._postgres_client.execute(
            """
            INSERT INTO indicators_1m (
                symbol,
                exchange,
                timeframe,
                bar_start_time,
                ema_7,
                ema_9,
                sma_3,
                sma_5
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, bar_start_time)
            DO UPDATE SET
                exchange = EXCLUDED.exchange,
                ema_7 = EXCLUDED.ema_7,
                ema_9 = EXCLUDED.ema_9,
                sma_3 = EXCLUDED.sma_3,
                sma_5 = EXCLUDED.sma_5
            """,
            (
                event.payload.symbol,
                event.payload.exchange,
                event.payload.timeframe,
                event.payload.bar_start_time,
                event.payload.values.ema_7,
                event.payload.values.ema_9,
                event.payload.values.sma_3,
                event.payload.values.sma_5,
            ),
        )
        self._logger.info(
            "indicator_upserted",
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
            bar_start_time=event.payload.bar_start_time.isoformat(),
        )

    def count_indicators(self) -> int | None:
        row = self._postgres_client.fetch_one("SELECT COUNT(*) FROM indicators_1m")
        if row is None:
            return None
        return int(row[0])

    def fetch_indicators(self) -> list[tuple] | None:
        if not self._postgres_client._settings.postgres_enabled:
            self._logger.info(
                "indicator_fetch_skipped",
                reason="postgres_disabled",
            )
            return None

        if self._postgres_client._connection is None:
            raise RuntimeError("Postgres client is not connected")

        with self._postgres_client._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    symbol,
                    exchange,
                    timeframe,
                    bar_start_time,
                    ema_7,
                    ema_9,
                    sma_3,
                    sma_5
                FROM indicators_1m
                ORDER BY bar_start_time ASC
                """
            )
            rows = cursor.fetchall()

        self._logger.info(
            "indicators_fetched",
            record_count=len(rows),
        )
        return rows
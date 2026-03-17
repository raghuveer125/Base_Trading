from __future__ import annotations

from shared.logging.logger import get_logger
from shared.models import BarEvent
from shared.postgres.client import PostgresClient


class ClosedBarRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client
        self._logger = get_logger("bar_builder.repository")

    def ensure_table(self) -> None:
        self._postgres_client.execute(
            """
            CREATE TABLE IF NOT EXISTS closed_bars_1m (
                id BIGSERIAL PRIMARY KEY,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                bar_start_time TIMESTAMPTZ NOT NULL,
                bar_end_time TIMESTAMPTZ NOT NULL,
                open NUMERIC(18, 6) NOT NULL,
                high NUMERIC(18, 6) NOT NULL,
                low NUMERIC(18, 6) NOT NULL,
                close NUMERIC(18, 6) NOT NULL,
                volume BIGINT NOT NULL,
                source_detail TEXT NOT NULL,
                revision INT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )

        self._postgres_client.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'closed_bars_1m_symbol_timeframe_bar_start_time_key'
                ) THEN
                    ALTER TABLE closed_bars_1m
                    ADD CONSTRAINT closed_bars_1m_symbol_timeframe_bar_start_time_key
                    UNIQUE (symbol, timeframe, bar_start_time);
                END IF;
            END
            $$;
            """
        )

        self._logger.info(
            "closed_bar_table_ready",
            table="closed_bars_1m",
        )

    def upsert_closed_bar(self, event: BarEvent) -> None:
        self._postgres_client.execute(
            """
            INSERT INTO closed_bars_1m (
                symbol,
                exchange,
                timeframe,
                bar_start_time,
                bar_end_time,
                open,
                high,
                low,
                close,
                volume,
                source_detail,
                revision
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (symbol, timeframe, bar_start_time)
            DO UPDATE SET
                exchange = EXCLUDED.exchange,
                bar_end_time = EXCLUDED.bar_end_time,
                open = EXCLUDED.open,
                high = EXCLUDED.high,
                low = EXCLUDED.low,
                close = EXCLUDED.close,
                volume = EXCLUDED.volume,
                source_detail = EXCLUDED.source_detail,
                revision = EXCLUDED.revision
            """,
            (
                event.payload.symbol,
                event.payload.exchange,
                event.payload.timeframe,
                event.payload.bar_start_time,
                event.payload.bar_end_time,
                event.payload.open,
                event.payload.high,
                event.payload.low,
                event.payload.close,
                event.payload.volume,
                event.payload.source_detail,
                event.payload.revision,
            ),
        )
        self._logger.info(
            "closed_bar_upserted",
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
            bar_start_time=event.payload.bar_start_time.isoformat(),
        )

    def count_closed_bars(self) -> int | None:
        row = self._postgres_client.fetch_one("SELECT COUNT(*) FROM closed_bars_1m")
        if row is None:
            return None
        return int(row[0])

    def fetch_closed_bars(self) -> list[tuple] | None:
        if not self._postgres_client._settings.postgres_enabled:
            self._logger.info(
                "closed_bar_fetch_skipped",
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
                    bar_end_time,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    source_detail,
                    revision
                FROM closed_bars_1m
                ORDER BY bar_start_time ASC
                """
            )
            rows = cursor.fetchall()

        self._logger.info(
            "closed_bars_fetched",
            record_count=len(rows),
        )
        return rows
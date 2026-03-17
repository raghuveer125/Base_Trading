from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from services.execution_service.app.models import OrderEventView, OrderLifecycleView
from services.execution_service.app.order_state_machine import OrderEvent, OrderStatus
from shared.postgres.client import PostgresClient


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PersistedOrder:
    order_id: str
    symbol: str
    side: str
    quantity: int
    broker: str
    current_status: str
    external_order_id: str | None
    correlation_id: str | None
    idempotency_key: str | None
    latest_message: str | None
    last_updated_at: datetime | None


class OrderPersistenceRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client

    def ensure_tables(self) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    broker TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    external_order_id TEXT,
                    correlation_id TEXT,
                    idempotency_key TEXT,
                    latest_message TEXT,
                    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_orders_external_order_id
                ON execution_orders (external_order_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_orders_correlation_id
                ON execution_orders (correlation_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_orders_idempotency_key
                ON execution_orders (idempotency_key)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_order_events (
                    id BIGSERIAL PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL,
                    message TEXT,
                    filled_quantity INTEGER NOT NULL DEFAULT 0,
                    remaining_quantity INTEGER,
                    average_price DOUBLE PRECISION,
                    raw_payload JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_order_events_order_id_event_time
                ON execution_order_events (order_id, event_time)
                """
            )
        self._postgres_client.commit()

    def upsert_order(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        broker: str,
        current_status: OrderStatus,
        external_order_id: str | None,
        correlation_id: str | None,
        idempotency_key: str | None,
        latest_message: str | None,
        last_updated_at: datetime | None,
    ) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_orders (
                    order_id,
                    symbol,
                    side,
                    quantity,
                    broker,
                    current_status,
                    external_order_id,
                    correlation_id,
                    idempotency_key,
                    latest_message,
                    last_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO UPDATE
                SET
                    symbol = EXCLUDED.symbol,
                    side = EXCLUDED.side,
                    quantity = EXCLUDED.quantity,
                    broker = EXCLUDED.broker,
                    current_status = EXCLUDED.current_status,
                    external_order_id = EXCLUDED.external_order_id,
                    correlation_id = EXCLUDED.correlation_id,
                    idempotency_key = EXCLUDED.idempotency_key,
                    latest_message = EXCLUDED.latest_message,
                    last_updated_at = EXCLUDED.last_updated_at
                """,
                (
                    order_id,
                    symbol,
                    side,
                    quantity,
                    broker,
                    current_status.value,
                    external_order_id,
                    correlation_id,
                    idempotency_key,
                    latest_message,
                    last_updated_at or utc_now(),
                ),
            )
        self._postgres_client.commit()

    def insert_event(self, event: OrderEvent) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_order_events (
                    order_id,
                    from_status,
                    to_status,
                    event_type,
                    event_time,
                    message,
                    filled_quantity,
                    remaining_quantity,
                    average_price,
                    raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    event.order_id,
                    event.from_status.value,
                    event.to_status.value,
                    event.event_type,
                    event.event_time,
                    event.message,
                    event.filled_quantity,
                    event.remaining_quantity,
                    event.average_price,
                    json.dumps(event.raw_payload) if event.raw_payload is not None else None,
                ),
            )
        self._postgres_client.commit()

    def get_order(self, order_id: str) -> PersistedOrder | None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    order_id,
                    symbol,
                    side,
                    quantity,
                    broker,
                    current_status,
                    external_order_id,
                    correlation_id,
                    idempotency_key,
                    latest_message,
                    last_updated_at
                FROM execution_orders
                WHERE order_id = %s
                """,
                (order_id,),
            )
            row = cur.fetchone()

        if row is None:
            return None

        return PersistedOrder(
            order_id=row[0],
            symbol=row[1],
            side=row[2],
            quantity=row[3],
            broker=row[4],
            current_status=row[5],
            external_order_id=row[6],
            correlation_id=row[7],
            idempotency_key=row[8],
            latest_message=row[9],
            last_updated_at=row[10],
        )

    def list_orders(self) -> list[OrderLifecycleView]:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    eo.order_id,
                    eo.symbol,
                    eo.side,
                    eo.quantity,
                    eo.broker,
                    eo.current_status,
                    eo.external_order_id,
                    eo.correlation_id,
                    eo.idempotency_key,
                    eo.latest_message,
                    eo.last_updated_at,
                    COUNT(eoe.id) AS history_count
                FROM execution_orders eo
                LEFT JOIN execution_order_events eoe
                    ON eo.order_id = eoe.order_id
                GROUP BY
                    eo.order_id,
                    eo.symbol,
                    eo.side,
                    eo.quantity,
                    eo.broker,
                    eo.current_status,
                    eo.external_order_id,
                    eo.correlation_id,
                    eo.idempotency_key,
                    eo.latest_message,
                    eo.last_updated_at
                ORDER BY eo.last_updated_at DESC NULLS LAST, eo.order_id DESC
                """
            )
            rows = cur.fetchall()

        result: list[OrderLifecycleView] = []
        for row in rows:
            result.append(
                OrderLifecycleView(
                    order_id=row[0],
                    symbol=row[1],
                    side=row[2],
                    quantity=row[3],
                    broker=row[4],
                    current_status=OrderStatus(row[5]),
                    history_count=int(row[10]),
                    external_order_id=row[6],
                    correlation_id=row[7],
                    idempotency_key=row[8],
                    latest_message=row[9],
                    last_updated_at=row[10 - 1],
                )
            )
        return result

    def get_history(self, order_id: str) -> list[OrderEventView]:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    order_id,
                    from_status,
                    to_status,
                    event_type,
                    event_time,
                    message,
                    filled_quantity,
                    remaining_quantity,
                    average_price,
                    raw_payload
                FROM execution_order_events
                WHERE order_id = %s
                ORDER BY event_time ASC, id ASC
                """,
                (order_id,),
            )
            rows = cur.fetchall()

        history: list[OrderEventView] = []
        for row in rows:
            history.append(
                OrderEventView(
                    order_id=row[0],
                    from_status=OrderStatus(row[1]),
                    to_status=OrderStatus(row[2]),
                    event_type=row[3],
                    event_time=row[4],
                    message=row[5],
                    filled_quantity=row[6],
                    remaining_quantity=row[7],
                    average_price=row[8],
                    raw_payload=row[9],
                )
            )
        return history

    def active_order_count(self) -> int:
        terminal_values = (
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value,
        )
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM execution_orders
                WHERE current_status NOT IN (%s, %s, %s)
                """,
                terminal_values,
            )
            row = cur.fetchone()
        return int(row[0]) if row is not None else 0

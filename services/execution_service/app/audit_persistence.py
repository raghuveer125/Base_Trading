from __future__ import annotations

import json
from services.execution_service.app.audit import AuditEvent
from shared.postgres.client import PostgresClient


class AuditPersistenceRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client

    def ensure_tables(self) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_audit_events (
                    audit_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL,
                    order_id TEXT,
                    symbol TEXT,
                    actor TEXT NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_audit_events_order_id_event_time
                ON execution_audit_events (order_id, event_time)
                """
            )
        self._postgres_client.commit()

    def append(self, event: AuditEvent) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_audit_events (
                    audit_id,
                    event_type,
                    message,
                    event_time,
                    order_id,
                    symbol,
                    actor,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    event.audit_id,
                    event.event_type,
                    event.message,
                    event.event_time,
                    event.order_id,
                    event.symbol,
                    event.actor,
                    json.dumps(event.metadata) if event.metadata is not None else None,
                ),
            )
        self._postgres_client.commit()

    def list_events(self, *, order_id: str | None = None, limit: int | None = None) -> list[AuditEvent]:
        query = """
            SELECT audit_id, event_type, message, event_time, order_id, symbol, actor, metadata
            FROM execution_audit_events
        """
        params: list[object] = []
        if order_id is not None:
            query += " WHERE order_id = %s"
            params.append(order_id)
        query += " ORDER BY event_time ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self._postgres_client.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [
            AuditEvent(
                audit_id=row[0],
                event_type=row[1],
                message=row[2],
                event_time=row[3],
                order_id=row[4],
                symbol=row[5],
                actor=row[6],
                metadata=row[7],
            )
            for row in rows
        ]

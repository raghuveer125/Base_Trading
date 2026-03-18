from __future__ import annotations

import json
from services.execution_service.app.trades import Trade
from shared.postgres.client import PostgresClient


class TradePersistenceRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client

    def ensure_tables(self) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    entry_side TEXT NOT NULL,
                    entry_quantity INTEGER NOT NULL,
                    entry_price DOUBLE PRECISION NOT NULL,
                    entry_time TIMESTAMPTZ NOT NULL,
                    exit_quantity INTEGER NOT NULL,
                    exit_price DOUBLE PRECISION,
                    exit_time TIMESTAMPTZ,
                    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
                    status TEXT NOT NULL,
                    entry_order_id TEXT,
                    exit_order_id TEXT,
                    metadata JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_trades_symbol_entry_time
                ON execution_trades (symbol, entry_time)
                """
            )
        self._postgres_client.commit()

    def insert_trade(self, trade: Trade) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_trades (
                    trade_id,
                    symbol,
                    entry_side,
                    entry_quantity,
                    entry_price,
                    entry_time,
                    exit_quantity,
                    exit_price,
                    exit_time,
                    realized_pnl,
                    status,
                    entry_order_id,
                    exit_order_id,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (trade_id) DO NOTHING
                """,
                (
                    trade.trade_id,
                    trade.symbol,
                    trade.entry_side,
                    trade.entry_quantity,
                    trade.entry_price,
                    trade.entry_time,
                    trade.exit_quantity,
                    trade.exit_price,
                    trade.exit_time,
                    trade.realized_pnl,
                    trade.status,
                    trade.entry_order_id,
                    trade.exit_order_id,
                    json.dumps(trade.metadata) if trade.metadata is not None else None,
                ),
            )
        self._postgres_client.commit()

    def list_trades(self, *, symbol: str | None = None) -> list[Trade]:
        query = """
            SELECT
                trade_id, symbol, entry_side, entry_quantity, entry_price, entry_time,
                exit_quantity, exit_price, exit_time, realized_pnl, status,
                entry_order_id, exit_order_id, metadata
            FROM execution_trades
        """
        params: list[object] = []
        if symbol is not None:
            query += " WHERE symbol = %s"
            params.append(symbol)
        query += " ORDER BY entry_time ASC"

        with self._postgres_client.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [
            Trade(
                trade_id=row[0],
                symbol=row[1],
                entry_side=row[2],
                entry_quantity=row[3],
                entry_price=row[4],
                entry_time=row[5],
                exit_quantity=row[6],
                exit_price=row[7],
                exit_time=row[8],
                realized_pnl=row[9],
                status=row[10],
                entry_order_id=row[11],
                exit_order_id=row[12],
                metadata=row[13],
            )
            for row in rows
        ]

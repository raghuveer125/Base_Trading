from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from services.execution_service.app.models import PositionLotView, PositionView
from services.execution_service.app.positions import PositionSnapshot
from shared.postgres.client import PostgresClient


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PersistedPosition:
    symbol: str
    net_quantity: int
    avg_price: float
    side: str
    realized_pnl: float
    updated_at: datetime


class PositionPersistenceRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client

    def ensure_tables(self) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_positions (
                    symbol TEXT PRIMARY KEY,
                    net_quantity INTEGER NOT NULL,
                    avg_price DOUBLE PRECISION NOT NULL,
                    side TEXT NOT NULL,
                    realized_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_position_lots (
                    id BIGSERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    lot_index INTEGER NOT NULL,
                    quantity INTEGER NOT NULL,
                    price DOUBLE PRECISION NOT NULL,
                    side TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_execution_position_lots_symbol_lot_index
                ON execution_position_lots (symbol, lot_index)
                """
            )
        self._postgres_client.commit()

    def upsert_position(self, snapshot: PositionSnapshot) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_positions (
                    symbol,
                    net_quantity,
                    avg_price,
                    side,
                    realized_pnl,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE
                SET
                    net_quantity = EXCLUDED.net_quantity,
                    avg_price = EXCLUDED.avg_price,
                    side = EXCLUDED.side,
                    realized_pnl = EXCLUDED.realized_pnl,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    snapshot.symbol,
                    snapshot.net_quantity,
                    snapshot.avg_price,
                    snapshot.side,
                    snapshot.realized_pnl,
                    snapshot.updated_at,
                ),
            )
            cur.execute(
                "DELETE FROM execution_position_lots WHERE symbol = %s",
                (snapshot.symbol,),
            )
            for idx, lot in enumerate(snapshot.open_lots):
                cur.execute(
                    """
                    INSERT INTO execution_position_lots (
                        symbol,
                        lot_index,
                        quantity,
                        price,
                        side,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        snapshot.symbol,
                        idx,
                        lot.quantity,
                        lot.price,
                        lot.side,
                        snapshot.updated_at,
                    ),
                )
        self._postgres_client.commit()

    def get_position(self, symbol: str) -> PositionView | None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT symbol, net_quantity, avg_price, side, realized_pnl, updated_at
                FROM execution_positions
                WHERE symbol = %s
                """,
                (symbol,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            cur.execute(
                """
                SELECT quantity, price, side
                FROM execution_position_lots
                WHERE symbol = %s
                ORDER BY lot_index ASC
                """,
                (symbol,),
            )
            lots = cur.fetchall()

        return PositionView(
            symbol=row[0],
            net_quantity=row[1],
            avg_price=row[2],
            side=row[3],
            realized_pnl=row[4],
            open_lots=[
                PositionLotView(quantity=lot[0], price=lot[1], side=lot[2])
                for lot in lots
            ],
            updated_at=row[5],
        )

    def list_positions(self) -> list[PositionView]:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT symbol
                FROM execution_positions
                ORDER BY symbol ASC
                """
            )
            rows = cur.fetchall()

        result: list[PositionView] = []
        for row in rows:
            position = self.get_position(row[0])
            if position is not None:
                result.append(position)
        return result

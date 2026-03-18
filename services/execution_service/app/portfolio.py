from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from services.execution_service.app.positions import PositionSnapshot


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PortfolioSnapshot:
    open_position_count: int
    gross_quantity: int
    net_quantity: int
    realized_pnl: float
    long_position_count: int
    short_position_count: int
    symbols: list[str]
    updated_at: datetime


class PortfolioService:
    def build_snapshot(self, positions: list[PositionSnapshot]) -> PortfolioSnapshot:
        open_positions = [p for p in positions if p.net_quantity != 0]
        gross_quantity = sum(abs(p.net_quantity) for p in open_positions)
        net_quantity = sum(p.net_quantity for p in open_positions)
        realized_pnl = round(sum(p.realized_pnl for p in positions), 6)
        long_count = sum(1 for p in open_positions if p.net_quantity > 0)
        short_count = sum(1 for p in open_positions if p.net_quantity < 0)
        symbols = sorted(p.symbol for p in open_positions)

        latest_updated_at = max((p.updated_at for p in positions), default=utc_now())

        return PortfolioSnapshot(
            open_position_count=len(open_positions),
            gross_quantity=gross_quantity,
            net_quantity=net_quantity,
            realized_pnl=realized_pnl,
            long_position_count=long_count,
            short_position_count=short_count,
            symbols=symbols,
            updated_at=latest_updated_at,
        )

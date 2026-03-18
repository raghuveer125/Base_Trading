from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from services.execution_service.app.positions import PositionSnapshot


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PositionPnlSnapshot:
    symbol: str
    side: str
    net_quantity: int
    avg_price: float
    mark_price: float
    unrealized_pnl: float
    realized_pnl: float
    total_pnl: float
    updated_at: datetime


@dataclass(slots=True)
class PortfolioPnlSnapshot:
    positions: list[PositionPnlSnapshot]
    realized_pnl: float
    unrealized_pnl: float
    total_pnl: float
    updated_at: datetime


class PriceStore:
    def __init__(self) -> None:
        self._marks: dict[str, float] = {}

    def set_mark(self, symbol: str, price: float) -> None:
        self._marks[symbol] = price

    def get_mark(self, symbol: str) -> float | None:
        return self._marks.get(symbol)

    def all_marks(self) -> dict[str, float]:
        return dict(self._marks)


class PnlService:
    def __init__(self, price_store: PriceStore | None = None) -> None:
        self._price_store = price_store or PriceStore()

    @property
    def price_store(self) -> PriceStore:
        return self._price_store

    def build_position_snapshot(
        self,
        position: PositionSnapshot,
        *,
        mark_price: float | None = None,
    ) -> PositionPnlSnapshot:
        effective_mark = mark_price if mark_price is not None else self._price_store.get_mark(position.symbol)
        if effective_mark is None:
            effective_mark = position.avg_price

        unrealized = self._compute_unrealized(
            side=position.side,
            net_quantity=position.net_quantity,
            avg_price=position.avg_price,
            mark_price=effective_mark,
        )
        realized = round(position.realized_pnl, 6)
        total = round(realized + unrealized, 6)

        return PositionPnlSnapshot(
            symbol=position.symbol,
            side=position.side,
            net_quantity=position.net_quantity,
            avg_price=position.avg_price,
            mark_price=effective_mark,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            total_pnl=total,
            updated_at=position.updated_at,
        )

    def build_portfolio_snapshot(self, positions: list[PositionSnapshot]) -> PortfolioPnlSnapshot:
        position_snaps = [self.build_position_snapshot(p) for p in positions]
        realized = round(sum(p.realized_pnl for p in position_snaps), 6)
        unrealized = round(sum(p.unrealized_pnl for p in position_snaps), 6)
        total = round(realized + unrealized, 6)
        updated_at = max((p.updated_at for p in position_snaps), default=utc_now())

        return PortfolioPnlSnapshot(
            positions=position_snaps,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=total,
            updated_at=updated_at,
        )

    def _compute_unrealized(
        self,
        *,
        side: str,
        net_quantity: int,
        avg_price: float,
        mark_price: float,
    ) -> float:
        if net_quantity == 0:
            return 0.0
        if side == "LONG":
            return round((mark_price - avg_price) * abs(net_quantity), 6)
        if side == "SHORT":
            return round((avg_price - mark_price) * abs(net_quantity), 6)
        return 0.0

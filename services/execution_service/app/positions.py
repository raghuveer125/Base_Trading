from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PositionLot:
    quantity: int
    price: float
    side: str


@dataclass(slots=True)
class PositionSnapshot:
    symbol: str
    net_quantity: int
    avg_price: float
    side: str
    realized_pnl: float
    open_lots: list[PositionLot]
    updated_at: datetime


@dataclass(slots=True)
class FillEvent:
    order_id: str
    symbol: str
    fill_quantity: int
    fill_price: float
    side: str
    event_time: datetime
    raw_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class InMemoryPosition:
    symbol: str
    open_lots: list[PositionLot] = field(default_factory=list)
    realized_pnl: float = 0.0
    updated_at: datetime = field(default_factory=utc_now)

    def net_quantity(self) -> int:
        qty = 0
        for lot in self.open_lots:
            qty += lot.quantity if lot.side == "BUY" else -lot.quantity
        return qty

    def avg_price(self) -> float:
        if not self.open_lots:
            return 0.0
        total_qty = 0
        total_value = 0.0
        for lot in self.open_lots:
            total_qty += lot.quantity
            total_value += lot.quantity * lot.price
        return 0.0 if total_qty == 0 else total_value / total_qty

    def side(self) -> str:
        net = self.net_quantity()
        if net > 0:
            return "LONG"
        if net < 0:
            return "SHORT"
        return "FLAT"


class PositionService:
    def __init__(self) -> None:
        self._positions: dict[str, InMemoryPosition] = {}

    def _get_or_create(self, symbol: str) -> InMemoryPosition:
        if symbol not in self._positions:
            self._positions[symbol] = InMemoryPosition(symbol=symbol)
        return self._positions[symbol]

    def apply_fill(self, fill: FillEvent) -> PositionSnapshot:
        position = self._get_or_create(fill.symbol)
        remaining = fill.fill_quantity
        incoming_side = fill.side.upper()

        if incoming_side == "BUY":
            remaining = self._close_short_lots(position, remaining, fill.fill_price)
            if remaining > 0:
                position.open_lots.append(PositionLot(quantity=remaining, price=fill.fill_price, side="BUY"))
        elif incoming_side == "SELL":
            remaining = self._close_long_lots(position, remaining, fill.fill_price)
            if remaining > 0:
                position.open_lots.append(PositionLot(quantity=remaining, price=fill.fill_price, side="SELL"))
        else:
            raise ValueError("fill side must be BUY or SELL")

        position.updated_at = fill.event_time
        return self.get_position(fill.symbol)

    def _close_short_lots(self, position: InMemoryPosition, incoming_qty: int, incoming_price: float) -> int:
        remaining = incoming_qty
        new_lots: list[PositionLot] = []

        for lot in position.open_lots:
            if remaining == 0 or lot.side != "SELL":
                new_lots.append(lot)
                continue

            matched = min(remaining, lot.quantity)
            position.realized_pnl += (lot.price - incoming_price) * matched
            left_qty = lot.quantity - matched
            remaining -= matched

            if left_qty > 0:
                new_lots.append(PositionLot(quantity=left_qty, price=lot.price, side=lot.side))

        for lot in position.open_lots:
            if lot.side == "BUY":
                new_lots.append(lot)

        position.open_lots = self._normalize_lots(new_lots)
        return remaining

    def _close_long_lots(self, position: InMemoryPosition, incoming_qty: int, incoming_price: float) -> int:
        remaining = incoming_qty
        new_lots: list[PositionLot] = []

        for lot in position.open_lots:
            if remaining == 0 or lot.side != "BUY":
                new_lots.append(lot)
                continue

            matched = min(remaining, lot.quantity)
            position.realized_pnl += (incoming_price - lot.price) * matched
            left_qty = lot.quantity - matched
            remaining -= matched

            if left_qty > 0:
                new_lots.append(PositionLot(quantity=left_qty, price=lot.price, side=lot.side))

        for lot in position.open_lots:
            if lot.side == "SELL":
                new_lots.append(lot)

        position.open_lots = self._normalize_lots(new_lots)
        return remaining

    def _normalize_lots(self, lots: list[PositionLot]) -> list[PositionLot]:
        return [lot for lot in lots if lot.quantity > 0]

    def get_position(self, symbol: str) -> PositionSnapshot:
        position = self._get_or_create(symbol)
        return PositionSnapshot(
            symbol=symbol,
            net_quantity=position.net_quantity(),
            avg_price=position.avg_price(),
            side=position.side(),
            realized_pnl=round(position.realized_pnl, 6),
            open_lots=list(position.open_lots),
            updated_at=position.updated_at,
        )

    def list_positions(self) -> list[PositionSnapshot]:
        return [self.get_position(symbol) for symbol in sorted(self._positions.keys())]

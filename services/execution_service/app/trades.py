from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class Trade:
    trade_id: str
    symbol: str
    entry_side: str
    entry_quantity: int
    entry_price: float
    entry_time: datetime
    exit_quantity: int = 0
    exit_price: float | None = None
    exit_time: datetime | None = None
    realized_pnl: float = 0.0
    status: str = "OPEN"
    entry_order_id: str | None = None
    exit_order_id: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class OpenLot:
    symbol: str
    side: str
    quantity: int
    price: float
    event_time: datetime
    order_id: str | None = None


@dataclass(slots=True)
class FillForLedger:
    order_id: str
    symbol: str
    side: str
    quantity: int
    price: float
    event_time: datetime
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class InMemoryTradeLedger:
    _open_lots: dict[str, list[OpenLot]] = field(default_factory=dict)
    _trades: list[Trade] = field(default_factory=list)

    def apply_fill(self, fill: FillForLedger) -> list[Trade]:
        symbol_lots = self._open_lots.setdefault(fill.symbol, [])
        generated: list[Trade] = []
        incoming_side = fill.side.upper()
        remaining = fill.quantity

        opposite_side = "SELL" if incoming_side == "BUY" else "BUY"
        surviving_lots: list[OpenLot] = []

        for lot in symbol_lots:
            if remaining == 0:
                surviving_lots.append(lot)
                continue

            if lot.side != opposite_side:
                surviving_lots.append(lot)
                continue

            matched = min(remaining, lot.quantity)
            pnl = self._compute_pnl(
                entry_side=lot.side,
                entry_price=lot.price,
                exit_price=fill.price,
                quantity=matched,
            )
            trade = Trade(
                trade_id=f"trd-{fill.symbol.replace(':', '_')}-{len(self._trades) + len(generated) + 1:06d}",
                symbol=fill.symbol,
                entry_side=lot.side,
                entry_quantity=matched,
                entry_price=lot.price,
                entry_time=lot.event_time,
                exit_quantity=matched,
                exit_price=fill.price,
                exit_time=fill.event_time,
                realized_pnl=round(pnl, 6),
                status="CLOSED",
                entry_order_id=lot.order_id,
                exit_order_id=fill.order_id,
                metadata=fill.metadata,
            )
            generated.append(trade)

            leftover = lot.quantity - matched
            remaining -= matched
            if leftover > 0:
                surviving_lots.append(
                    OpenLot(
                        symbol=lot.symbol,
                        side=lot.side,
                        quantity=leftover,
                        price=lot.price,
                        event_time=lot.event_time,
                        order_id=lot.order_id,
                    )
                )

        if remaining > 0:
            surviving_lots.append(
                OpenLot(
                    symbol=fill.symbol,
                    side=incoming_side,
                    quantity=remaining,
                    price=fill.price,
                    event_time=fill.event_time,
                    order_id=fill.order_id,
                )
            )

        self._open_lots[fill.symbol] = surviving_lots
        self._trades.extend(generated)
        return generated

    def _compute_pnl(self, *, entry_side: str, entry_price: float, exit_price: float, quantity: int) -> float:
        if entry_side == "BUY":
            return (exit_price - entry_price) * quantity
        return (entry_price - exit_price) * quantity

    def list_trades(self, *, symbol: str | None = None) -> list[Trade]:
        trades = self._trades
        if symbol is not None:
            trades = [t for t in trades if t.symbol == symbol]
        return list(trades)

    def list_open_lots(self, *, symbol: str | None = None) -> list[OpenLot]:
        if symbol is not None:
            return list(self._open_lots.get(symbol, []))
        result: list[OpenLot] = []
        for lots in self._open_lots.values():
            result.extend(lots)
        return result

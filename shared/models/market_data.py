from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from shared.models.base import BaseEvent, EventMetadata
from shared.models.enums import EventType


class TickData(BaseModel):
    symbol: str
    exchange: str
    last_traded_price: Decimal
    last_traded_quantity: int | None = None
    last_trade_time: datetime
    received_at: datetime


class TickEvent(BaseEvent):
    payload: TickData

    @classmethod
    def create(
        cls,
        source: str,
        symbol: str,
        exchange: str,
        last_traded_price: Decimal,
        last_trade_time: datetime,
        received_at: datetime,
        last_traded_quantity: int | None = None,
    ) -> "TickEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.TICK,
                source=source,
            ),
            payload=TickData(
                symbol=symbol,
                exchange=exchange,
                last_traded_price=last_traded_price,
                last_traded_quantity=last_traded_quantity,
                last_trade_time=last_trade_time,
                received_at=received_at,
            ),
        )


class QuoteData(BaseModel):
    symbol: str
    exchange: str
    bid_price: Decimal
    ask_price: Decimal
    bid_quantity: int | None = None
    ask_quantity: int | None = None
    received_at: datetime


class QuoteEvent(BaseEvent):
    payload: QuoteData

    @classmethod
    def create(
        cls,
        source: str,
        symbol: str,
        exchange: str,
        bid_price: Decimal,
        ask_price: Decimal,
        received_at: datetime,
        bid_quantity: int | None = None,
        ask_quantity: int | None = None,
    ) -> "QuoteEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.QUOTE,
                source=source,
            ),
            payload=QuoteData(
                symbol=symbol,
                exchange=exchange,
                bid_price=bid_price,
                ask_price=ask_price,
                bid_quantity=bid_quantity,
                ask_quantity=ask_quantity,
                received_at=received_at,
            ),
        )
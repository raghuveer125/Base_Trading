from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from shared.models.base import BaseEvent, EventMetadata
from shared.models.enums import EventType


class BarData(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    bar_start_time: datetime
    bar_end_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source_detail: str
    revision: int = 1


class BarEvent(BaseEvent):
    payload: BarData

    @classmethod
    def create(
        cls,
        source: str,
        symbol: str,
        exchange: str,
        timeframe: str,
        bar_start_time: datetime,
        bar_end_time: datetime,
        open_price: Decimal,
        high_price: Decimal,
        low_price: Decimal,
        close_price: Decimal,
        volume: int,
        source_detail: str,
        revision: int = 1,
    ) -> "BarEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.BAR,
                source=source,
            ),
            payload=BarData(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                bar_start_time=bar_start_time,
                bar_end_time=bar_end_time,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                source_detail=source_detail,
                revision=revision,
            ),
        )
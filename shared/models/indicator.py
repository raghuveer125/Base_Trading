from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from shared.models.base import BaseEvent, EventMetadata
from shared.models.enums import EventType


class IndicatorValues(BaseModel):
    ema_7: Decimal | None = None
    ema_9: Decimal | None = None
    sma_3: Decimal | None = None
    sma_5: Decimal | None = None


class IndicatorData(BaseModel):
    symbol: str
    exchange: str
    timeframe: str
    bar_start_time: datetime
    values: IndicatorValues


class IndicatorEvent(BaseEvent):
    payload: IndicatorData

    @classmethod
    def create(
        cls,
        source: str,
        symbol: str,
        exchange: str,
        timeframe: str,
        bar_start_time: datetime,
        values: IndicatorValues,
    ) -> "IndicatorEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.INDICATOR,
                source=source,
            ),
            payload=IndicatorData(
                symbol=symbol,
                exchange=exchange,
                timeframe=timeframe,
                bar_start_time=bar_start_time,
                values=values,
            ),
        )
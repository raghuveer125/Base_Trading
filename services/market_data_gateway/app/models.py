from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class GatewayStatus(BaseModel):
    service: str
    mode: str
    connected: bool
    subscribed_symbols: list[str]
    last_emit_at: datetime | None = None
    message: str


class RawMarketPacket(BaseModel):
    symbol: str
    exchange: str
    ltp: Decimal
    ltq: int | None = None
    last_trade_time: datetime
    received_at: datetime = Field(default_factory=utc_now)
    raw_payload: dict[str, Any] | None = None
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class BarBuilderStatus(BaseModel):
    service: str
    mode: str
    connected: bool
    source_topic: str
    target_topic: str
    closed_topic: str
    timeframe: str
    consumed_count: int
    produced_count: int
    closed_count: int
    open_bar_count: int
    last_processed_at: datetime | None = None
    message: str
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReplayStatus(BaseModel):
    service: str
    replay_ready: bool
    source_table: str
    records_loaded: int
    message: str
    updated_at: datetime = utc_now()
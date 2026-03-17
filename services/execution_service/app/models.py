from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionServiceStatus(BaseModel):
    service: str
    mode: str
    broker: str
    replay_ready: bool
    approved_loaded: int
    orders_prepared: int
    last_prepared_at: datetime | None = None
    message: str
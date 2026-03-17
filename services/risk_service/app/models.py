from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class RiskServiceStatus(BaseModel):
    service: str
    mode: str
    replay_ready: bool
    source: str
    signals_loaded: int
    approved_signals: int
    rejected_signals: int
    last_evaluated_at: datetime | None = None
    message: str
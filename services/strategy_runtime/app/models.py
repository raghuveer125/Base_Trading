from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel


def utc_now() -> datetime:
    return datetime.now(UTC)


class StrategyRuntimeStatus(BaseModel):
    service: str
    strategy_name: str
    mode: str
    replay_ready: bool
    source_table: str
    records_loaded: int
    generated_signals: int
    last_evaluated_at: datetime | None = None
    message: str
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class EventMetadata(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    event_version: str = "1.0"
    source: str
    created_at: datetime = Field(default_factory=utc_now)
    correlation_id: str | None = None


class BaseEvent(BaseModel):
    meta: EventMetadata
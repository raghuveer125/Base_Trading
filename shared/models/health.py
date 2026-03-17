from __future__ import annotations

from pydantic import BaseModel

from shared.models.base import BaseEvent, EventMetadata
from shared.models.enums import EventType


class HealthStatus(BaseModel):
    service: str
    status: str
    env: str


class HealthEvent(BaseEvent):
    payload: HealthStatus

    @classmethod
    def create(cls, service: str, status: str, env: str) -> "HealthEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.HEALTH,
                source=service,
            ),
            payload=HealthStatus(
                service=service,
                status=status,
                env=env,
            ),
        )
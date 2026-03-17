from __future__ import annotations

from pydantic import BaseModel

from shared.models.base import BaseEvent, EventMetadata
from shared.models.enums import EventType


class ErrorData(BaseModel):
    service: str
    code: str
    message: str
    details: dict[str, str] | None = None


class ErrorEvent(BaseEvent):
    payload: ErrorData

    @classmethod
    def create(
        cls,
        source: str,
        code: str,
        message: str,
        details: dict[str, str] | None = None,
    ) -> "ErrorEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.ERROR,
                source=source,
            ),
            payload=ErrorData(
                service=source,
                code=code,
                message=message,
                details=details,
            ),
        )
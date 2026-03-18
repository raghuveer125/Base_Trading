from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class AuditEvent:
    audit_id: str
    event_type: str
    message: str
    event_time: datetime
    order_id: str | None = None
    symbol: str | None = None
    actor: str = "system"
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class InMemoryAuditTrail:
    _events: list[AuditEvent] = field(default_factory=list)

    def append(self, event: AuditEvent) -> AuditEvent:
        self._events.append(event)
        return event

    def list_events(self, *, order_id: str | None = None, limit: int | None = None) -> list[AuditEvent]:
        events = self._events
        if order_id is not None:
            events = [e for e in events if e.order_id == order_id]
        events = sorted(events, key=lambda e: e.event_time)
        if limit is not None:
            events = events[-limit:]
        return list(events)

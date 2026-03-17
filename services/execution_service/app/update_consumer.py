from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class BrokerUpdateEnvelope:
    source: str
    received_at: datetime
    order_id: str | None
    external_order_id: str | None
    broker_status: str
    payload: dict[str, Any]


class BrokerUpdateConsumer:
    def normalize_update(
        self,
        payload: dict[str, Any],
        *,
        source: str = "api",
    ) -> BrokerUpdateEnvelope:
        broker_status = str(
            payload.get("broker_status")
            or payload.get("status")
            or payload.get("order_status")
            or ""
        ).strip()
        if not broker_status:
            raise ValueError("broker_status is required")

        order_id = payload.get("order_id")
        external_order_id = payload.get("external_order_id") or payload.get("orderId") or payload.get("id")

        return BrokerUpdateEnvelope(
            source=source,
            received_at=utc_now(),
            order_id=str(order_id) if order_id else None,
            external_order_id=str(external_order_id) if external_order_id else None,
            broker_status=broker_status,
            payload=dict(payload),
        )

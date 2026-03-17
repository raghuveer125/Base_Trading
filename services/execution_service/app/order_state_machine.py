from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


class OrderStatus(StrEnum):
    CREATED = "created"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


TERMINAL_STATES: set[OrderStatus] = {
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
}


ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.CREATED: {
        OrderStatus.SUBMITTED,
        OrderStatus.REJECTED,
        OrderStatus.ERROR,
    },
    OrderStatus.SUBMITTED: {
        OrderStatus.ACKNOWLEDGED,
        OrderStatus.OPEN,
        OrderStatus.REJECTED,
        OrderStatus.ERROR,
    },
    OrderStatus.ACKNOWLEDGED: {
        OrderStatus.OPEN,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.ERROR,
    },
    OrderStatus.OPEN: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELLED,
        OrderStatus.REJECTED,
        OrderStatus.ERROR,
    },
    OrderStatus.PARTIALLY_FILLED: {
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.CANCEL_PENDING,
        OrderStatus.CANCELLED,
        OrderStatus.ERROR,
    },
    OrderStatus.CANCEL_PENDING: {
        OrderStatus.CANCELLED,
        OrderStatus.PARTIALLY_FILLED,
        OrderStatus.FILLED,
        OrderStatus.ERROR,
    },
    OrderStatus.FILLED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.ERROR: set(),
}


BROKER_STATUS_MAP: dict[str, OrderStatus] = {
    "TRANSIT": OrderStatus.SUBMITTED,
    "PENDING": OrderStatus.SUBMITTED,
    "TRIGGER PENDING": OrderStatus.SUBMITTED,
    "PUT ORDER REQ RECEIVED": OrderStatus.SUBMITTED,
    "VALIDATION PENDING": OrderStatus.SUBMITTED,
    "OPEN": OrderStatus.OPEN,
    "NEW": OrderStatus.ACKNOWLEDGED,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "COMPLETE": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "CANCELED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "FAILED": OrderStatus.ERROR,
    "ERROR": OrderStatus.ERROR,
}


@dataclass(slots=True)
class OrderEvent:
    order_id: str
    from_status: OrderStatus
    to_status: OrderStatus
    event_type: str
    event_time: datetime
    message: str | None = None
    raw_payload: dict[str, Any] | None = None
    filled_quantity: int = 0
    remaining_quantity: int | None = None
    average_price: float | None = None


class InvalidOrderTransition(ValueError):
    pass


def normalize_broker_status(status: str) -> OrderStatus:
    normalized = status.strip().upper().replace("-", "_")
    if normalized in BROKER_STATUS_MAP:
        return BROKER_STATUS_MAP[normalized]
    raise ValueError(f"Unsupported broker status: {status}")


class OrderStateMachine:
    def can_transition(self, current: OrderStatus, target: OrderStatus) -> bool:
        return target in ALLOWED_TRANSITIONS[current]

    def transition(
        self,
        *,
        order_id: str,
        current: OrderStatus,
        target: OrderStatus,
        event_type: str,
        message: str | None = None,
        raw_payload: dict[str, Any] | None = None,
        filled_quantity: int = 0,
        remaining_quantity: int | None = None,
        average_price: float | None = None,
        event_time: datetime | None = None,
    ) -> OrderEvent:
        if not self.can_transition(current, target):
            raise InvalidOrderTransition(
                f"Invalid transition for order {order_id}: {current.value} -> {target.value}"
            )

        return OrderEvent(
            order_id=order_id,
            from_status=current,
            to_status=target,
            event_type=event_type,
            event_time=event_time or utc_now(),
            message=message,
            raw_payload=raw_payload,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            average_price=average_price,
        )

    def transition_from_broker_update(
        self,
        *,
        order_id: str,
        current: OrderStatus,
        broker_status: str,
        raw_payload: dict[str, Any] | None = None,
    ) -> OrderEvent:
        target = normalize_broker_status(broker_status)
        filled_quantity = 0
        remaining_quantity = None
        average_price = None

        if raw_payload:
            filled_quantity = int(raw_payload.get("filledQty") or raw_payload.get("filled_qty") or 0)
            remaining_raw = raw_payload.get("remainingQty") or raw_payload.get("remaining_qty")
            remaining_quantity = int(remaining_raw) if remaining_raw is not None else None
            avg_raw = raw_payload.get("avgPrice") or raw_payload.get("average_price")
            average_price = float(avg_raw) if avg_raw is not None else None

        return self.transition(
            order_id=order_id,
            current=current,
            target=target,
            event_type="broker_update",
            message=f"Broker update mapped from {broker_status}",
            raw_payload=raw_payload,
            filled_quantity=filled_quantity,
            remaining_quantity=remaining_quantity,
            average_price=average_price,
        )

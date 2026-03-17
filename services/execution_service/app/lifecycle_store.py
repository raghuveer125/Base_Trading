from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from services.execution_service.app.models import OrderEventView, OrderLifecycleView
from services.execution_service.app.order_state_machine import OrderEvent, OrderStatus


@dataclass(slots=True)
class StoredOrder:
    order_id: str
    symbol: str
    side: str
    quantity: int
    broker: str
    current_status: OrderStatus
    external_order_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    latest_message: str | None = None
    last_updated_at: datetime | None = None
    history: list[OrderEvent] = field(default_factory=list)


class InMemoryOrderLifecycleStore:
    def __init__(self) -> None:
        self._orders: dict[str, StoredOrder] = {}

    def create_order(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        broker: str,
        correlation_id: str | None,
        idempotency_key: str | None,
    ) -> StoredOrder:
        stored = StoredOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            broker=broker,
            current_status=OrderStatus.CREATED,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        self._orders[order_id] = stored
        return stored

    def exists(self, order_id: str) -> bool:
        return order_id in self._orders

    def get(self, order_id: str) -> StoredOrder:
        return self._orders[order_id]

    def append_event(self, order_id: str, event: OrderEvent, external_order_id: str | None = None) -> StoredOrder:
        stored = self._orders[order_id]
        stored.current_status = event.to_status
        stored.latest_message = event.message
        stored.last_updated_at = event.event_time
        if external_order_id:
            stored.external_order_id = external_order_id
        stored.history.append(event)
        return stored

    def list_orders(self) -> list[OrderLifecycleView]:
        views: list[OrderLifecycleView] = []
        for stored in self._orders.values():
            views.append(
                OrderLifecycleView(
                    order_id=stored.order_id,
                    symbol=stored.symbol,
                    side=stored.side,
                    quantity=stored.quantity,
                    broker=stored.broker,
                    current_status=stored.current_status,
                    history_count=len(stored.history),
                    external_order_id=stored.external_order_id,
                    correlation_id=stored.correlation_id,
                    idempotency_key=stored.idempotency_key,
                    latest_message=stored.latest_message,
                    last_updated_at=stored.last_updated_at or datetime.now(),
                )
            )
        return views

    def get_history(self, order_id: str) -> list[OrderEventView]:
        stored = self._orders[order_id]
        return [
            OrderEventView(
                order_id=event.order_id,
                from_status=event.from_status,
                to_status=event.to_status,
                event_type=event.event_type,
                event_time=event.event_time,
                message=event.message,
                filled_quantity=event.filled_quantity,
                remaining_quantity=event.remaining_quantity,
                average_price=event.average_price,
                raw_payload=event.raw_payload,
            )
            for event in stored.history
        ]

    def active_order_count(self) -> int:
        active = 0
        for stored in self._orders.values():
            if stored.current_status not in {
                OrderStatus.FILLED,
                OrderStatus.CANCELLED,
                OrderStatus.REJECTED,
            }:
                active += 1
        return active

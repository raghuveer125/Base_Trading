from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel

from shared.models.base import BaseEvent, EventMetadata
from shared.models.enums import EventType


class OrderCommandData(BaseModel):
    strategy_id: str
    symbol: str
    exchange: str
    side: str
    order_type: str
    quantity: int
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    product_type: str | None = None
    idempotency_key: str


class OrderCommandEvent(BaseEvent):
    payload: OrderCommandData

    @classmethod
    def create(
        cls,
        source: str,
        strategy_id: str,
        symbol: str,
        exchange: str,
        side: str,
        order_type: str,
        quantity: int,
        idempotency_key: str,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        product_type: str | None = None,
    ) -> "OrderCommandEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.ORDER_COMMAND,
                source=source,
            ),
            payload=OrderCommandData(
                strategy_id=strategy_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                trigger_price=trigger_price,
                product_type=product_type,
                idempotency_key=idempotency_key,
            ),
        )


class OrderUpdateData(BaseModel):
    broker_order_id: str
    symbol: str
    status: str
    message: str | None = None


class OrderUpdateEvent(BaseEvent):
    payload: OrderUpdateData

    @classmethod
    def create(
        cls,
        source: str,
        broker_order_id: str,
        symbol: str,
        status: str,
        message: str | None = None,
    ) -> "OrderUpdateEvent":
        return cls(
            meta=EventMetadata(
                event_type=EventType.ORDER_UPDATE,
                source=source,
            ),
            payload=OrderUpdateData(
                broker_order_id=broker_order_id,
                symbol=symbol,
                status=status,
                message=message,
            ),
        )
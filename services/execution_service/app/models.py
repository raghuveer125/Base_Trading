from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


class BrokerHealth(BaseModel):
    broker: str
    adapter: str
    mode: str
    ready: bool
    has_client_id: bool
    has_access_token: bool
    checked_at: datetime = Field(default_factory=utc_now)
    message: str


class BrokerPlaceOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    validity: str = "DAY"
    limit_price: float = 0.0
    stop_price: float = 0.0
    disclosed_qty: int = 0
    offline_order: bool = False
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy_name: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    source_bar_time: str | None = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return normalized

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}
        if normalized not in allowed:
            raise ValueError(f"order_type must be one of {sorted(allowed)}")
        return normalized

    @field_validator("product")
    @classmethod
    def validate_product(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"INTRADAY", "CNC", "MARGIN", "CO", "BO"}
        if normalized not in allowed:
            raise ValueError(f"product must be one of {sorted(allowed)}")
        return normalized

    @field_validator("validity")
    @classmethod
    def validate_validity(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"DAY", "IOC"}
        if normalized not in allowed:
            raise ValueError(f"validity must be one of {sorted(allowed)}")
        return normalized


class BrokerPlaceOrderResponse(BaseModel):
    broker: str
    adapter: str
    accepted: bool
    status: str
    external_order_id: str | None = None
    processed_at: datetime = Field(default_factory=utc_now)
    message: str
    correlation_id: str | None = None
    idempotency_key: str | None = None
    raw_response: dict[str, Any] | None = None


class ExecutionServiceStatus(BaseModel):
    service: str
    mode: str
    broker: str
    broker_adapter: str
    broker_mode: str
    broker_ready: bool
    replay_ready: bool
    approved_loaded: int
    orders_prepared: int
    last_prepared_at: datetime | None = None
    message: str

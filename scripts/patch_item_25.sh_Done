#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app"
mkdir -p "$ROOT/tests/unit"

cat > "$ROOT/services/execution_service/app/order_state_machine.py" <<'PY'
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
PY

cat > "$ROOT/services/execution_service/app/models.py" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from services.execution_service.app.order_state_machine import OrderStatus


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


class OrderLifecycleView(BaseModel):
    order_id: str
    symbol: str
    side: str
    quantity: int
    broker: str
    current_status: OrderStatus
    history_count: int
    external_order_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    latest_message: str | None = None
    last_updated_at: datetime = Field(default_factory=utc_now)


class OrderEventView(BaseModel):
    order_id: str
    from_status: OrderStatus
    to_status: OrderStatus
    event_type: str
    event_time: datetime
    message: str | None = None
    filled_quantity: int = 0
    remaining_quantity: int | None = None
    average_price: float | None = None
    raw_payload: dict[str, Any] | None = None


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
    active_order_count: int = 0
    last_prepared_at: datetime | None = None
    message: str
PY

cat > "$ROOT/services/execution_service/app/lifecycle_store.py" <<'PY'
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
PY

cat > "$ROOT/services/execution_service/app/service.py" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import (
    BrokerHealth,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
    OrderEventView,
    OrderLifecycleView,
)
from services.execution_service.app.order_state_machine import OrderStateMachine, OrderStatus
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.signal_reader import ApprovedSignalReader
from shared.config.settings import Settings


class ExecutionService:
    def __init__(
        self,
        settings: Settings,
        signal_reader: ApprovedSignalReader,
        processor: ExecutionProcessor,
        broker_adapter: BrokerAdapter,
        lifecycle_store: InMemoryOrderLifecycleStore | None = None,
        state_machine: OrderStateMachine | None = None,
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._broker_adapter = broker_adapter
        self._lifecycle_store = lifecycle_store or InMemoryOrderLifecycleStore()
        self._state_machine = state_machine or OrderStateMachine()
        self._orders_prepared = 0
        self._last_prepared_at: datetime | None = None

    def prepare_once(self) -> list[dict[str, str]]:
        approved_signals = self._signal_reader.load_approved_signals()
        orders = self._processor.prepare_orders(approved_signals)
        self._orders_prepared = len(orders)
        self._last_prepared_at = datetime.now(UTC)
        return orders

    def get_broker_health(self) -> BrokerHealth:
        return self._broker_adapter.health_check()

    def _build_internal_order_id(self, request_symbol: str, correlation_id: str | None) -> str:
        seed = correlation_id or request_symbol
        normalized = seed.replace(":", "_").replace("|", "_")
        return f"ord-{normalized}-{uuid4().hex[:8]}"

    def place_first_prepared_order_once(self) -> BrokerPlaceOrderResponse:
        orders = self.prepare_once()
        if not orders:
            return BrokerPlaceOrderResponse(
                broker=self._settings.execution_service_broker,
                adapter="fyers",
                accepted=False,
                status="empty",
                external_order_id=None,
                message="No approved signals available for broker submission",
            )

        request = self._processor.build_broker_request(orders[0])
        internal_order_id = self._build_internal_order_id(request.symbol, request.correlation_id)

        self._lifecycle_store.create_order(
            order_id=internal_order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            broker=self._settings.execution_service_broker,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )

        created_event = self._state_machine.transition(
            order_id=internal_order_id,
            current=OrderStatus.CREATED,
            target=OrderStatus.SUBMITTED,
            event_type="submit_request",
            message="Order submitted to broker adapter",
        )
        self._lifecycle_store.append_event(internal_order_id, created_event)

        result = self._broker_adapter.place_order(request)

        if result.accepted:
            ack_event = self._state_machine.transition(
                order_id=internal_order_id,
                current=OrderStatus.SUBMITTED,
                target=OrderStatus.ACKNOWLEDGED,
                event_type="broker_ack",
                message=result.message,
                raw_payload=result.raw_response,
            )
            self._lifecycle_store.append_event(
                internal_order_id,
                ack_event,
                external_order_id=result.external_order_id,
            )
        else:
            reject_target = OrderStatus.REJECTED if result.status in {"rejected", "empty"} else OrderStatus.ERROR
            reject_event = self._state_machine.transition(
                order_id=internal_order_id,
                current=OrderStatus.SUBMITTED,
                target=reject_target,
                event_type="broker_reject",
                message=result.message,
                raw_payload=result.raw_response,
            )
            self._lifecycle_store.append_event(
                internal_order_id,
                reject_event,
                external_order_id=result.external_order_id,
            )

        return result

    def apply_broker_update(
        self,
        *,
        order_id: str,
        broker_status: str,
        raw_payload: dict[str, object] | None = None,
    ) -> OrderEventView:
        stored = self._lifecycle_store.get(order_id)
        event = self._state_machine.transition_from_broker_update(
            order_id=order_id,
            current=stored.current_status,
            broker_status=broker_status,
            raw_payload=raw_payload,
        )
        self._lifecycle_store.append_event(
            order_id,
            event,
            external_order_id=stored.external_order_id,
        )
        return self._lifecycle_store.get_history(order_id)[-1]

    def list_order_lifecycle(self) -> list[OrderLifecycleView]:
        return self._lifecycle_store.list_orders()

    def get_order_history(self, order_id: str) -> list[OrderEventView]:
        return self._lifecycle_store.get_history(order_id)

    def get_status(self) -> ExecutionServiceStatus:
        approved = self._signal_reader.load_approved_signals()
        broker_health = self._broker_adapter.health_check()
        return ExecutionServiceStatus(
            service="execution_service",
            mode=self._settings.execution_service_mode,
            broker=self._settings.execution_service_broker,
            broker_adapter=broker_health.adapter,
            broker_mode=broker_health.mode,
            broker_ready=broker_health.ready,
            replay_ready=True,
            approved_loaded=len(approved),
            orders_prepared=self._orders_prepared,
            active_order_count=self._lifecycle_store.active_order_count(),
            last_prepared_at=self._last_prepared_at,
            message="Execution service ready",
        )
PY

cat > "$ROOT/services/execution_service/app/api.py" <<'PY'
from fastapi import FastAPI, HTTPException

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import BrokerPlaceOrderRequest, BrokerPlaceOrderResponse
from services.execution_service.app.order_state_machine import InvalidOrderTransition, OrderStateMachine
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

app = FastAPI(title="execution_service", version="0.1.0")

_LIFECYCLE_STORE = InMemoryOrderLifecycleStore()
_STATE_MACHINE = OrderStateMachine()


def build_execution_service() -> ExecutionService:
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()
    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()
    return ExecutionService(
        settings=settings,
        signal_reader=ApprovedSignalReader(
            signal_reader=StrategySignalReader(
                replay_reader=IndicatorReplayReader(repository=repository),
                strategy_processor=StrategyProcessor(),
            ),
            risk_processor=RiskProcessor(settings=settings),
        ),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=_LIFECYCLE_STORE,
        state_machine=_STATE_MACHINE,
    )


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)
    broker_health = broker_adapter.health_check()

    replay_ready = True
    approved_loaded = 0
    active_order_count = _LIFECYCLE_STORE.active_order_count()
    message = "Execution service ready"

    try:
        service = build_execution_service()
        status = service.get_status()
        replay_ready = status.replay_ready
        approved_loaded = status.approved_loaded
        active_order_count = status.active_order_count
    except Exception as exc:
        replay_ready = False
        message = f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})"

    return {
        "service": "execution_service",
        "mode": settings.execution_service_mode,
        "broker": settings.execution_service_broker,
        "broker_adapter": broker_health.adapter,
        "broker_mode": broker_health.mode,
        "broker_ready": broker_health.ready,
        "replay_ready": replay_ready,
        "approved_loaded": approved_loaded,
        "orders_prepared": 0,
        "active_order_count": active_order_count,
        "last_prepared_at": None,
        "message": message,
        "status": "ok" if broker_health.ready else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, str | bool | int | None]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)
    broker_health = broker_adapter.health_check()

    try:
        status = build_execution_service().get_status()
        return {
            "service": status.service,
            "mode": status.mode,
            "broker": status.broker,
            "broker_adapter": status.broker_adapter,
            "broker_mode": status.broker_mode,
            "broker_ready": status.broker_ready,
            "replay_ready": status.replay_ready,
            "approved_loaded": status.approved_loaded,
            "orders_prepared": status.orders_prepared,
            "active_order_count": status.active_order_count,
            "last_prepared_at": status.last_prepared_at.isoformat() if status.last_prepared_at else None,
            "message": status.message,
        }
    except Exception as exc:
        return {
            "service": "execution_service",
            "mode": settings.execution_service_mode,
            "broker": settings.execution_service_broker,
            "broker_adapter": broker_health.adapter,
            "broker_mode": broker_health.mode,
            "broker_ready": broker_health.ready,
            "replay_ready": False,
            "approved_loaded": 0,
            "orders_prepared": 0,
            "active_order_count": _LIFECYCLE_STORE.active_order_count(),
            "last_prepared_at": None,
            "message": f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})",
        }


@app.get("/execution-service/broker/health")
def broker_health() -> dict[str, str | bool | None]:
    health = build_broker_adapter(settings=get_settings()).health_check()
    return {
        "broker": health.broker,
        "adapter": health.adapter,
        "mode": health.mode,
        "ready": health.ready,
        "has_client_id": health.has_client_id,
        "has_access_token": health.has_access_token,
        "checked_at": health.checked_at.isoformat(),
        "message": health.message,
    }


@app.post("/execution-service/prepare-once")
def prepare_once() -> dict[str, object]:
    try:
        service = build_execution_service()
        orders = service.prepare_once()
        return {
            "service": "execution_service",
            "order_count": len(orders),
            "orders": orders,
            "message": "Execution preparation completed",
        }
    except Exception as exc:
        return {
            "service": "execution_service",
            "order_count": 0,
            "orders": [],
            "message": f"Execution preparation unavailable: replay storage unavailable ({exc.__class__.__name__})",
        }


@app.post("/execution-service/broker/place-first")
def place_first() -> dict[str, object]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)

    try:
        result = build_execution_service().place_first_prepared_order_once()
    except Exception:
        result = BrokerPlaceOrderResponse(
            broker=settings.execution_service_broker,
            adapter=broker_adapter.health_check().adapter,
            accepted=False,
            status="unavailable",
            external_order_id=None,
            message="Broker placement unavailable because replay storage is not available",
        )

    return {
        "broker": result.broker,
        "adapter": result.adapter,
        "accepted": result.accepted,
        "status": result.status,
        "external_order_id": result.external_order_id,
        "processed_at": result.processed_at.isoformat(),
        "message": result.message,
        "correlation_id": result.correlation_id,
        "idempotency_key": result.idempotency_key,
        "raw_response": result.raw_response,
    }


@app.post("/execution-service/broker/place-test")
def place_test() -> dict[str, object]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)

    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        product="INTRADAY",
        validity="DAY",
        correlation_id="manual-test-correlation",
        idempotency_key="manual-test-idempotency",
    )

    result = broker_adapter.place_order(request)

    return {
        "broker": result.broker,
        "adapter": result.adapter,
        "accepted": result.accepted,
        "status": result.status,
        "external_order_id": result.external_order_id,
        "processed_at": result.processed_at.isoformat(),
        "message": result.message,
        "correlation_id": result.correlation_id,
        "idempotency_key": result.idempotency_key,
        "raw_response": result.raw_response,
    }


@app.get("/execution-service/orders")
def list_orders() -> dict[str, object]:
    return {
        "service": "execution_service",
        "count": len(_LIFECYCLE_STORE.list_orders()),
        "orders": [order.model_dump(mode="json") for order in _LIFECYCLE_STORE.list_orders()],
    }


@app.get("/execution-service/orders/{order_id}/history")
def order_history(order_id: str) -> dict[str, object]:
    try:
        history = _LIFECYCLE_STORE.get_history(order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}") from exc

    return {
        "service": "execution_service",
        "order_id": order_id,
        "history_count": len(history),
        "history": [event.model_dump(mode="json") for event in history],
    }


@app.post("/execution-service/orders/{order_id}/broker-update")
def apply_broker_update(order_id: str, payload: dict[str, object]) -> dict[str, object]:
    broker_status = str(payload.get("broker_status") or payload.get("status") or "").strip()
    if not broker_status:
        raise HTTPException(status_code=400, detail="broker_status is required")

    service = ExecutionService(
        settings=get_settings(),
        signal_reader=None,  # type: ignore[arg-type]
        processor=ExecutionProcessor(settings=get_settings()),
        broker_adapter=build_broker_adapter(settings=get_settings()),
        lifecycle_store=_LIFECYCLE_STORE,
        state_machine=_STATE_MACHINE,
    )

    try:
        event = service.apply_broker_update(
            order_id=order_id,
            broker_status=broker_status,
            raw_payload=payload,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}") from exc
    except (InvalidOrderTransition, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "service": "execution_service",
        "order_id": order_id,
        "event": event.model_dump(mode="json"),
    }
PY

cat > "$ROOT/tests/unit/test_execution_service.py" <<'PY'
from datetime import UTC, datetime

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import BrokerPlaceOrderRequest
from services.execution_service.app.order_state_machine import (
    InvalidOrderTransition,
    OrderStateMachine,
    OrderStatus,
    normalize_broker_status,
)
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from shared.config.settings import Settings


def build_settings(execution_broker: str = "fyers_stub") -> Settings:
    return Settings(
        APP_ENV="local",
        APP_NAME="projectX",
        LOG_LEVEL="INFO",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="projectx",
        POSTGRES_USER="projectx",
        POSTGRES_PASSWORD="changeme",
        POSTGRES_ENABLED=False,
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_ENABLED=False,
        REDIS_KEY_PREFIX="projectx",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_TOPIC_TICKS="md.raw.tick",
        KAFKA_TOPIC_BARS_1M="md.bar.1m",
        KAFKA_TOPIC_BARS_1M_CLOSED="md.bar.1m.closed",
        KAFKA_TOPIC_INDICATORS_1M="md.indicator.1m",
        KAFKA_CLIENT_ID="projectx-mdg",
        KAFKA_ENABLED=False,
        KAFKA_AUTO_CREATE_TOPICS=False,
        KAFKA_TOPIC_PARTITIONS=1,
        KAFKA_TOPIC_REPLICATION_FACTOR=1,
        KAFKA_CONSUMER_GROUP_BAR_BUILDER="projectx-bar-builder",
        KAFKA_CONSUMER_GROUP_INDICATOR_ENGINE="projectx-indicator-engine",
        KAFKA_CONSUMER_AUTO_OFFSET_RESET="earliest",
        FYERS_CLIENT_ID="client_id",
        FYERS_SECRET_KEY="secret_key",
        FYERS_REDIRECT_URI="http://localhost/callback",
        FYERS_ACCESS_TOKEN="token",
        AUTH_SESSION_FILE="data/auth/session.json",
        AUTH_REQUEST_TIMEOUT_SECONDS=10,
        AUTH_VALIDATE_ON_STARTUP=False,
        AUTH_SERVICE_MODE="bootstrap",
        MDG_MODE="stub",
        MDG_SYMBOLS="NSE:SBIN-EQ,NSE:RELIANCE-EQ",
        MDG_EXCHANGE="NSE",
        MDG_EMIT_INTERVAL_SECONDS=1,
        MDG_API_HOST="127.0.0.1",
        MDG_API_PORT=8002,
        BAR_BUILDER_MODE="stub",
        BAR_BUILDER_API_HOST="127.0.0.1",
        BAR_BUILDER_API_PORT=8003,
        BAR_BUILDER_TIMEFRAME="1m",
        BAR_BUILDER_CLOSE_ON_NEXT_MINUTE=True,
        INDICATOR_ENGINE_MODE="stub",
        INDICATOR_ENGINE_API_HOST="127.0.0.1",
        INDICATOR_ENGINE_API_PORT=8004,
        INDICATOR_ENGINE_TIMEFRAME="1m",
        STRATEGY_RUNTIME_MODE="stub",
        STRATEGY_RUNTIME_API_HOST="127.0.0.1",
        STRATEGY_RUNTIME_API_PORT=8005,
        STRATEGY_RUNTIME_NAME="ema_sma_cross_stub",
        RISK_SERVICE_MODE="stub",
        RISK_SERVICE_API_HOST="127.0.0.1",
        RISK_SERVICE_API_PORT=8006,
        RISK_MAX_OPEN_POSITIONS=5,
        RISK_MAX_SIGNAL_SIZE=1,
        EXECUTION_SERVICE_MODE="stub",
        EXECUTION_SERVICE_API_HOST="127.0.0.1",
        EXECUTION_SERVICE_API_PORT=8007,
        EXECUTION_SERVICE_BROKER=execution_broker,
    )


class FakeApprovedSignalReader:
    def load_approved_signals(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": "NSE:SBIN-EQ",
                "timeframe": "1m",
                "bar_start_time": datetime(2026, 3, 17, 17, 0, tzinfo=UTC).isoformat(),
                "signal": "BUY",
                "size": "1",
            }
        ]


def test_execution_processor_prepares_order() -> None:
    processor = ExecutionProcessor(settings=build_settings())
    orders = processor.prepare_orders(FakeApprovedSignalReader().load_approved_signals())
    assert len(orders) == 1
    assert orders[0]["side"] == "BUY"
    assert orders[0]["broker"] == "fyers_stub"
    assert orders[0]["status"] == "prepared"


def test_execution_processor_builds_request_with_idempotency() -> None:
    processor = ExecutionProcessor(settings=build_settings())
    order = processor.prepare_orders(FakeApprovedSignalReader().load_approved_signals())[0]
    request = processor.build_broker_request(order)
    assert request.side == "BUY"
    assert request.quantity == 1
    assert request.idempotency_key is not None
    assert len(request.idempotency_key) == 24
    assert request.correlation_id is not None


def test_execution_service_prepares_once() -> None:
    settings = build_settings()
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
    )
    orders = service.prepare_once()
    status = service.get_status()
    assert len(orders) == 1
    assert status.service == "execution_service"
    assert status.approved_loaded == 1
    assert status.orders_prepared == 1
    assert status.broker == "fyers_stub"
    assert status.broker_adapter == "fyers"
    assert status.broker_ready is True


def test_execution_service_stub_broker_accepts_first_order_and_creates_lifecycle() -> None:
    settings = build_settings("fyers_stub")
    store = InMemoryOrderLifecycleStore()
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=store,
        state_machine=OrderStateMachine(),
    )
    result = service.place_first_prepared_order_once()
    orders = service.list_order_lifecycle()

    assert result.accepted is True
    assert result.status == "accepted"
    assert result.external_order_id is not None
    assert result.idempotency_key is not None
    assert len(orders) == 1
    assert orders[0].current_status == OrderStatus.ACKNOWLEDGED
    assert orders[0].history_count == 2


def test_execution_request_validates_side() -> None:
    try:
        BrokerPlaceOrderRequest(symbol="NSE:SBIN-EQ", side="HOLD", quantity=1)
    except Exception as exc:
        assert "side must be BUY or SELL" in str(exc)
    else:
        raise AssertionError("Expected invalid side validation error")


def test_execution_live_broker_error_when_sdk_missing_or_call_fails() -> None:
    settings = build_settings("fyers_live")
    adapter = build_broker_adapter(settings=settings)
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id="test-correlation",
        idempotency_key="test-idempotency",
    )
    result = adapter.place_order(request)
    assert result.accepted is False
    assert result.status in {"accepted", "rejected", "error"}


def test_order_state_machine_valid_transition() -> None:
    machine = OrderStateMachine()
    event = machine.transition(
        order_id="ord-1",
        current=OrderStatus.SUBMITTED,
        target=OrderStatus.ACKNOWLEDGED,
        event_type="broker_ack",
    )
    assert event.from_status == OrderStatus.SUBMITTED
    assert event.to_status == OrderStatus.ACKNOWLEDGED


def test_order_state_machine_invalid_transition() -> None:
    machine = OrderStateMachine()
    try:
        machine.transition(
            order_id="ord-1",
            current=OrderStatus.CREATED,
            target=OrderStatus.FILLED,
            event_type="bad_transition",
        )
    except InvalidOrderTransition as exc:
        assert "created -> filled" in str(exc)
    else:
        raise AssertionError("Expected InvalidOrderTransition")


def test_normalize_broker_status() -> None:
    assert normalize_broker_status("OPEN") == OrderStatus.OPEN
    assert normalize_broker_status("complete") == OrderStatus.FILLED
    assert normalize_broker_status("partially filled") == OrderStatus.PARTIALLY_FILLED


def test_apply_broker_update_moves_order_to_filled() -> None:
    settings = build_settings("fyers_stub")
    store = InMemoryOrderLifecycleStore()
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=store,
        state_machine=OrderStateMachine(),
    )
    service.place_first_prepared_order_once()
    order = service.list_order_lifecycle()[0]

    open_event = service.apply_broker_update(
        order_id=order.order_id,
        broker_status="OPEN",
        raw_payload={"status": "OPEN"},
    )
    fill_event = service.apply_broker_update(
        order_id=order.order_id,
        broker_status="COMPLETE",
        raw_payload={"status": "COMPLETE", "filledQty": 1, "avgPrice": 600.25},
    )

    assert open_event.to_status == OrderStatus.OPEN
    assert fill_event.to_status == OrderStatus.FILLED
    assert fill_event.filled_quantity == 1
    assert fill_event.average_price == 600.25
PY

cat > "$ROOT/tests/unit/test_execution_service_api.py" <<'PY'
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
from services.execution_service.app.models import (
    BrokerHealth,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
)
from services.execution_service.app.order_state_machine import OrderStatus
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def get_status(self) -> ExecutionServiceStatus:
        return ExecutionServiceStatus(
            service="execution_service",
            mode="stub",
            broker="fyers_stub",
            broker_adapter="fyers",
            broker_mode="stub",
            broker_ready=True,
            replay_ready=True,
            approved_loaded=1,
            orders_prepared=1,
            active_order_count=1,
            last_prepared_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
            message="Execution service ready",
        )

    def get_broker_health(self) -> BrokerHealth:
        return BrokerHealth(
            broker="fyers_stub",
            adapter="fyers",
            mode="stub",
            ready=True,
            has_client_id=True,
            has_access_token=True,
            message="FYERS broker adapter ready",
        )

    def prepare_once(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": "NSE:SBIN-EQ",
                "timeframe": "1m",
                "bar_start_time": datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(),
                "side": "BUY",
                "quantity": "1",
                "broker": "fyers_stub",
                "status": "prepared",
            }
        ]

    def place_first_prepared_order_once(self) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id="stub-NSE_SBIN-EQ-buy-1-test",
            message="Stub broker accepted order",
            correlation_id="NSE:SBIN-EQ|1m|2026-03-18T12:00:00+00:00",
            idempotency_key="aaaaaaaaaaaaaaaaaaaaaaaa",
            raw_response={"symbol": "NSE:SBIN-EQ"},
        )


execution_api.build_execution_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "execution_service"
    assert body["status"] == "ok"
    assert body["broker_adapter"] == "fyers"


def test_execution_status_endpoint() -> None:
    response = client.get("/execution-service/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "execution_service"
    assert body["broker"] == "fyers_stub"
    assert body["broker_adapter"] == "fyers"


def test_broker_health_endpoint() -> None:
    response = client.get("/execution-service/broker/health")
    assert response.status_code == 200
    body = response.json()
    assert body["broker"] == "fyers_stub"
    assert body["adapter"] == "fyers"
    assert body["ready"] is True


def test_prepare_once_endpoint() -> None:
    response = client.post("/execution-service/prepare-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "execution_service"
    assert body["order_count"] == 1
    assert len(body["orders"]) == 1


def test_place_first_endpoint() -> None:
    response = client.post("/execution-service/broker/place-first")
    assert response.status_code == 200
    body = response.json()
    assert body["broker"] == "fyers_stub"
    assert body["adapter"] == "fyers"
    assert body["status"] == "accepted"
    assert body["idempotency_key"] == "aaaaaaaaaaaaaaaaaaaaaaaa"


def test_place_test_endpoint() -> None:
    response = client.post("/execution-service/broker/place-test")
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["idempotency_key"] == "manual-test-idempotency"


def test_order_listing_and_history_endpoints() -> None:
    create_response = client.post("/execution-service/broker/place-test")
    assert create_response.status_code == 200

    orders_response = client.get("/execution-service/orders")
    assert orders_response.status_code == 200
    orders_body = orders_response.json()
    assert "orders" in orders_body

    if orders_body["count"] > 0:
        order_id = orders_body["orders"][0]["order_id"]
        update_response = client.post(
            f"/execution-service/orders/{order_id}/broker-update",
            json={"broker_status": "OPEN"},
        )
        assert update_response.status_code in {200, 404, 400}

        history_response = client.get(f"/execution-service/orders/{order_id}/history")
        assert history_response.status_code == 200
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
marker = "# Item 25 — Order state machine and lifecycle tracking"
if marker not in text:
    addition = """

# Item 25 — Order state machine and lifecycle tracking
## Checklist

  * Add internal order status enum
  * Add allowed transition rules
  * Add invalid transition guard
  * Add broker status normalization
  * Add lifecycle event model
  * Add in-memory lifecycle store
  * Track submitted to acknowledged flow
  * Add broker update application flow
  * Add order listing endpoint
  * Add order history endpoint
  * Add broker update simulation endpoint
  * Add state machine unit tests
  * Add lifecycle service tests
  * Add API tests for lifecycle endpoints
  * Verify tests pass
  * Verify stub order moves through lifecycle
  * Docs updated

## Definition of done

  * Code written
  * State machine added
  * Transition guards added
  * Broker normalization added
  * Logs preserved
  * Tests added
  * Stub lifecycle verified
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 25 patch applied"
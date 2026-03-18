#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app"
mkdir -p "$ROOT/tests/unit"

cat > "$ROOT/services/execution_service/app/positions.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PositionLot:
    quantity: int
    price: float
    side: str


@dataclass(slots=True)
class PositionSnapshot:
    symbol: str
    net_quantity: int
    avg_price: float
    side: str
    realized_pnl: float
    open_lots: list[PositionLot]
    updated_at: datetime


@dataclass(slots=True)
class FillEvent:
    order_id: str
    symbol: str
    fill_quantity: int
    fill_price: float
    side: str
    event_time: datetime
    raw_payload: dict[str, Any] | None = None


@dataclass(slots=True)
class InMemoryPosition:
    symbol: str
    open_lots: list[PositionLot] = field(default_factory=list)
    realized_pnl: float = 0.0
    updated_at: datetime = field(default_factory=utc_now)

    def net_quantity(self) -> int:
        qty = 0
        for lot in self.open_lots:
            qty += lot.quantity if lot.side == "BUY" else -lot.quantity
        return qty

    def avg_price(self) -> float:
        if not self.open_lots:
            return 0.0
        total_qty = 0
        total_value = 0.0
        for lot in self.open_lots:
            total_qty += lot.quantity
            total_value += lot.quantity * lot.price
        return 0.0 if total_qty == 0 else total_value / total_qty

    def side(self) -> str:
        net = self.net_quantity()
        if net > 0:
            return "LONG"
        if net < 0:
            return "SHORT"
        return "FLAT"


class PositionService:
    def __init__(self) -> None:
        self._positions: dict[str, InMemoryPosition] = {}

    def _get_or_create(self, symbol: str) -> InMemoryPosition:
        if symbol not in self._positions:
            self._positions[symbol] = InMemoryPosition(symbol=symbol)
        return self._positions[symbol]

    def apply_fill(self, fill: FillEvent) -> PositionSnapshot:
        position = self._get_or_create(fill.symbol)
        remaining = fill.fill_quantity
        incoming_side = fill.side.upper()

        if incoming_side == "BUY":
            remaining = self._close_short_lots(position, remaining, fill.fill_price)
            if remaining > 0:
                position.open_lots.append(PositionLot(quantity=remaining, price=fill.fill_price, side="BUY"))
        elif incoming_side == "SELL":
            remaining = self._close_long_lots(position, remaining, fill.fill_price)
            if remaining > 0:
                position.open_lots.append(PositionLot(quantity=remaining, price=fill.fill_price, side="SELL"))
        else:
            raise ValueError("fill side must be BUY or SELL")

        position.updated_at = fill.event_time
        return self.get_position(fill.symbol)

    def _close_short_lots(self, position: InMemoryPosition, incoming_qty: int, incoming_price: float) -> int:
        remaining = incoming_qty
        new_lots: list[PositionLot] = []

        for lot in position.open_lots:
            if remaining == 0 or lot.side != "SELL":
                new_lots.append(lot)
                continue

            matched = min(remaining, lot.quantity)
            position.realized_pnl += (lot.price - incoming_price) * matched
            left_qty = lot.quantity - matched
            remaining -= matched

            if left_qty > 0:
                new_lots.append(PositionLot(quantity=left_qty, price=lot.price, side=lot.side))

        for lot in position.open_lots:
            if lot.side == "BUY":
                new_lots.append(lot)

        position.open_lots = self._normalize_lots(new_lots)
        return remaining

    def _close_long_lots(self, position: InMemoryPosition, incoming_qty: int, incoming_price: float) -> int:
        remaining = incoming_qty
        new_lots: list[PositionLot] = []

        for lot in position.open_lots:
            if remaining == 0 or lot.side != "BUY":
                new_lots.append(lot)
                continue

            matched = min(remaining, lot.quantity)
            position.realized_pnl += (incoming_price - lot.price) * matched
            left_qty = lot.quantity - matched
            remaining -= matched

            if left_qty > 0:
                new_lots.append(PositionLot(quantity=left_qty, price=lot.price, side=lot.side))

        for lot in position.open_lots:
            if lot.side == "SELL":
                new_lots.append(lot)

        position.open_lots = self._normalize_lots(new_lots)
        return remaining

    def _normalize_lots(self, lots: list[PositionLot]) -> list[PositionLot]:
        return [lot for lot in lots if lot.quantity > 0]

    def get_position(self, symbol: str) -> PositionSnapshot:
        position = self._get_or_create(symbol)
        return PositionSnapshot(
            symbol=symbol,
            net_quantity=position.net_quantity(),
            avg_price=position.avg_price(),
            side=position.side(),
            realized_pnl=round(position.realized_pnl, 6),
            open_lots=list(position.open_lots),
            updated_at=position.updated_at,
        )

    def list_positions(self) -> list[PositionSnapshot]:
        return [self.get_position(symbol) for symbol in sorted(self._positions.keys())]
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


class BrokerCancelOrderRequest(BaseModel):
    order_id: str
    external_order_id: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None


class BrokerModifyOrderRequest(BaseModel):
    order_id: str
    external_order_id: str | None = None
    quantity: int | None = None
    limit_price: float | None = None
    stop_price: float | None = None
    order_type: str | None = None
    validity: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip().upper()
        allowed = {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}
        if normalized not in allowed:
            raise ValueError(f"order_type must be one of {sorted(allowed)}")
        return normalized

    @field_validator("validity")
    @classmethod
    def validate_validity(cls, value: str | None) -> str | None:
        if value is None:
            return value
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
    order_id: str | None = None
    duplicate_of_order_id: str | None = None


class BrokerActionResponse(BaseModel):
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
    order_id: str | None = None


class PositionLotView(BaseModel):
    quantity: int
    price: float
    side: str


class PositionView(BaseModel):
    symbol: str
    net_quantity: int
    avg_price: float
    side: str
    realized_pnl: float
    open_lots: list[PositionLotView]
    updated_at: datetime


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
    open_position_count: int = 0
    last_prepared_at: datetime | None = None
    message: str
PY

cat > "$ROOT/services/execution_service/app/service.py" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import (
    BrokerActionResponse,
    BrokerCancelOrderRequest,
    BrokerHealth,
    BrokerModifyOrderRequest,
    BrokerPlaceOrderRequest,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
    OrderEventView,
    OrderLifecycleView,
)
from services.execution_service.app.order_state_machine import OrderStateMachine, OrderStatus
from services.execution_service.app.persistence import OrderPersistenceRepository
from services.execution_service.app.positions import FillEvent, PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.execution_service.app.update_consumer import BrokerUpdateConsumer, BrokerUpdateEnvelope
from shared.config.settings import Settings


class DuplicateOrderSubmissionError(ValueError):
    pass


class UnknownBrokerUpdateOrderError(KeyError):
    pass


class OrderActionNotAllowedError(ValueError):
    pass


class ExecutionService:
    def __init__(
        self,
        settings: Settings,
        signal_reader: ApprovedSignalReader | None,
        processor: ExecutionProcessor,
        broker_adapter: BrokerAdapter,
        lifecycle_store: InMemoryOrderLifecycleStore | None = None,
        state_machine: OrderStateMachine | None = None,
        persistence_repository: OrderPersistenceRepository | None = None,
        update_consumer: BrokerUpdateConsumer | None = None,
        position_service: PositionService | None = None,
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._broker_adapter = broker_adapter
        self._lifecycle_store = lifecycle_store or InMemoryOrderLifecycleStore()
        self._state_machine = state_machine or OrderStateMachine()
        self._persistence_repository = persistence_repository
        self._update_consumer = update_consumer or BrokerUpdateConsumer()
        self._position_service = position_service or PositionService()
        self._orders_prepared = 0
        self._last_prepared_at: datetime | None = None

    def _persist_current_order(self, order_id: str) -> None:
        if self._persistence_repository is None:
            return
        stored = self._lifecycle_store.get(order_id)
        self._persistence_repository.upsert_order(
            order_id=stored.order_id,
            symbol=stored.symbol,
            side=stored.side,
            quantity=stored.quantity,
            broker=stored.broker,
            current_status=stored.current_status,
            external_order_id=stored.external_order_id,
            correlation_id=stored.correlation_id,
            idempotency_key=stored.idempotency_key,
            latest_message=stored.latest_message,
            last_updated_at=stored.last_updated_at,
        )

    def _persist_event(self, order_id: str) -> None:
        if self._persistence_repository is None:
            return
        event = self._lifecycle_store.get(order_id).history[-1]
        self._persistence_repository.insert_event(event)
        self._persist_current_order(order_id)

    def _find_duplicate_order_id(self, idempotency_key: str | None) -> str | None:
        if not idempotency_key:
            return None

        for order in self._lifecycle_store.list_orders():
            if order.idempotency_key == idempotency_key:
                return order.order_id

        if self._persistence_repository is not None:
            persisted = self._persistence_repository.get_order_by_idempotency_key(idempotency_key)
            if persisted is not None:
                return persisted.order_id

        return None

    def _build_duplicate_response(
        self,
        *,
        request: BrokerPlaceOrderRequest,
        order_id: str,
    ) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker=self._settings.execution_service_broker,
            adapter="fyers",
            accepted=True,
            status="duplicate",
            external_order_id=None,
            message=f"Duplicate idempotency key detected; reusing order {order_id}",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response={"duplicate": True, "order_id": order_id},
            order_id=order_id,
            duplicate_of_order_id=order_id,
        )

    def prepare_once(self) -> list[dict[str, str]]:
        if self._signal_reader is None:
            return []
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

    def _resolve_order_id_for_update(self, envelope: BrokerUpdateEnvelope) -> str:
        if envelope.order_id:
            if self._lifecycle_store.exists(envelope.order_id):
                return envelope.order_id
            if self._persistence_repository is not None:
                persisted = self._persistence_repository.get_order(envelope.order_id)
                if persisted is not None:
                    return persisted.order_id

        if envelope.external_order_id:
            stored = self._lifecycle_store.find_by_external_order_id(envelope.external_order_id)
            if stored is not None:
                return stored.order_id
            if self._persistence_repository is not None:
                persisted = self._persistence_repository.get_order_by_external_order_id(envelope.external_order_id)
                if persisted is not None:
                    return persisted.order_id

        raise UnknownBrokerUpdateOrderError(
            f"Unable to resolve order for broker update: order_id={envelope.order_id}, external_order_id={envelope.external_order_id}"
        )

    def _load_order(self, order_id: str):
        return self._lifecycle_store.get(order_id)

    def _ensure_cancel_allowed(self, status: OrderStatus) -> None:
        if status not in {OrderStatus.ACKNOWLEDGED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
            raise OrderActionNotAllowedError(f"Cancel not allowed from status {status.value}")

    def _ensure_modify_allowed(self, status: OrderStatus) -> None:
        if status not in {OrderStatus.ACKNOWLEDGED, OrderStatus.OPEN, OrderStatus.PARTIALLY_FILLED}:
            raise OrderActionNotAllowedError(f"Modify not allowed from status {status.value}")

    def submit_order_request(self, request: BrokerPlaceOrderRequest, submit_message: str) -> BrokerPlaceOrderResponse:
        duplicate_order_id = self._find_duplicate_order_id(request.idempotency_key)
        if duplicate_order_id is not None:
            return self._build_duplicate_response(request=request, order_id=duplicate_order_id)

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
        self._persist_current_order(internal_order_id)

        created_event = self._state_machine.transition(
            order_id=internal_order_id,
            current=OrderStatus.CREATED,
            target=OrderStatus.SUBMITTED,
            event_type="submit_request",
            message=submit_message,
        )
        self._lifecycle_store.append_event(internal_order_id, created_event)
        self._persist_event(internal_order_id)

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
            self._persist_event(internal_order_id)
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
            self._persist_event(internal_order_id)

        result.order_id = internal_order_id
        return result

    def register_manual_test_order(self, response: BrokerPlaceOrderResponse) -> str:
        request = BrokerPlaceOrderRequest(
            symbol="NSE:SBIN-EQ",
            side="BUY",
            quantity=1,
            order_type="MARKET",
            product="INTRADAY",
            validity="DAY",
            correlation_id=response.correlation_id,
            idempotency_key=response.idempotency_key,
        )
        duplicate_order_id = self._find_duplicate_order_id(request.idempotency_key)
        if duplicate_order_id is not None:
            return duplicate_order_id

        registered = self.submit_order_request(
            request=request,
            submit_message="Manual test order submitted to broker adapter",
        )
        return registered.order_id or ""

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
        return self.submit_order_request(
            request=request,
            submit_message="Order submitted to broker adapter",
        )

    def cancel_order(self, order_id: str) -> BrokerActionResponse:
        stored = self._load_order(order_id)
        self._ensure_cancel_allowed(stored.current_status)

        cancel_pending = self._state_machine.transition(
            order_id=order_id,
            current=stored.current_status,
            target=OrderStatus.CANCEL_PENDING,
            event_type="cancel_request",
            message="Cancel requested",
        )
        self._lifecycle_store.append_event(order_id, cancel_pending, external_order_id=stored.external_order_id)
        self._persist_event(order_id)

        request = BrokerCancelOrderRequest(
            order_id=order_id,
            external_order_id=stored.external_order_id,
            correlation_id=stored.correlation_id,
            idempotency_key=stored.idempotency_key,
        )
        result = self._broker_adapter.cancel_order(request)

        next_status = OrderStatus.CANCELLED if result.accepted else OrderStatus.ERROR
        event_type = "broker_cancel_ack" if result.accepted else "broker_cancel_reject"
        final_event = self._state_machine.transition(
            order_id=order_id,
            current=OrderStatus.CANCEL_PENDING,
            target=next_status,
            event_type=event_type,
            message=result.message,
            raw_payload=result.raw_response,
        )
        self._lifecycle_store.append_event(order_id, final_event, external_order_id=stored.external_order_id)
        self._persist_event(order_id)
        result.order_id = order_id
        return result

    def modify_order(
        self,
        order_id: str,
        *,
        quantity: int | None = None,
        limit_price: float | None = None,
        stop_price: float | None = None,
        order_type: str | None = None,
        validity: str | None = None,
    ) -> BrokerActionResponse:
        stored = self._load_order(order_id)
        self._ensure_modify_allowed(stored.current_status)

        request = BrokerModifyOrderRequest(
            order_id=order_id,
            external_order_id=stored.external_order_id,
            quantity=quantity,
            limit_price=limit_price,
            stop_price=stop_price,
            order_type=order_type,
            validity=validity,
            correlation_id=stored.correlation_id,
            idempotency_key=stored.idempotency_key,
        )
        result = self._broker_adapter.modify_order(request)

        if result.accepted:
            event = self._state_machine.transition(
                order_id=order_id,
                current=stored.current_status,
                target=stored.current_status,
                event_type="broker_modify_ack",
                message=result.message,
                raw_payload=result.raw_response,
            )
        else:
            event = self._state_machine.transition(
                order_id=order_id,
                current=stored.current_status,
                target=OrderStatus.ERROR,
                event_type="broker_modify_reject",
                message=result.message,
                raw_payload=result.raw_response,
            )
        self._lifecycle_store.append_event(order_id, event, external_order_id=stored.external_order_id)
        self._persist_event(order_id)
        result.order_id = order_id
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
        self._persist_event(order_id)

        if event.to_status == OrderStatus.FILLED:
            filled_quantity = int(event.filled_quantity or stored.quantity)
            avg_price = float(event.average_price or 0.0)
            if avg_price > 0 and filled_quantity > 0:
                self._position_service.apply_fill(
                    FillEvent(
                        order_id=order_id,
                        symbol=stored.symbol,
                        fill_quantity=filled_quantity,
                        fill_price=avg_price,
                        side=stored.side,
                        event_time=event.event_time,
                        raw_payload=event.raw_payload,
                    )
                )

        return self._lifecycle_store.get_history(order_id)[-1]

    def consume_broker_update(
        self,
        payload: dict[str, object],
        *,
        source: str = "api",
    ) -> OrderEventView:
        envelope = self._update_consumer.normalize_update(payload, source=source)
        resolved_order_id = self._resolve_order_id_for_update(envelope)
        merged_payload = dict(envelope.payload)
        merged_payload["update_source"] = envelope.source
        merged_payload["received_at"] = envelope.received_at.isoformat()
        if envelope.external_order_id:
            merged_payload["external_order_id"] = envelope.external_order_id
        return self.apply_broker_update(
            order_id=resolved_order_id,
            broker_status=envelope.broker_status,
            raw_payload=merged_payload,
        )

    def get_position(self, symbol: str):
        return self._position_service.get_position(symbol)

    def list_positions(self):
        return self._position_service.list_positions()

    def list_order_lifecycle(self) -> list[OrderLifecycleView]:
        if self._persistence_repository is not None:
            return self._persistence_repository.list_orders()
        return self._lifecycle_store.list_orders()

    def get_order_history(self, order_id: str) -> list[OrderEventView]:
        if self._persistence_repository is not None:
            return self._persistence_repository.get_history(order_id)
        return self._lifecycle_store.get_history(order_id)

    def get_status(self) -> ExecutionServiceStatus:
        approved = self._signal_reader.load_approved_signals() if self._signal_reader is not None else []
        broker_health = self._broker_adapter.health_check()
        active_order_count = (
            self._persistence_repository.active_order_count()
            if self._persistence_repository is not None
            else self._lifecycle_store.active_order_count()
        )
        open_position_count = len([p for p in self._position_service.list_positions() if p.net_quantity != 0])
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
            active_order_count=active_order_count,
            open_position_count=open_position_count,
            last_prepared_at=self._last_prepared_at,
            message="Execution service ready",
        )
PY

cat > "$ROOT/services/execution_service/app/api.py" <<'PY'
from fastapi import FastAPI, HTTPException

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import BrokerPlaceOrderRequest, BrokerPlaceOrderResponse, PositionLotView, PositionView
from services.execution_service.app.order_state_machine import InvalidOrderTransition, OrderStateMachine
from services.execution_service.app.persistence import OrderPersistenceRepository
from services.execution_service.app.positions import PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import (
    ExecutionService,
    OrderActionNotAllowedError,
    UnknownBrokerUpdateOrderError,
)
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.execution_service.app.update_consumer import BrokerUpdateConsumer
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
_UPDATE_CONSUMER = BrokerUpdateConsumer()
_POSITION_SERVICE = PositionService()


def _build_persistence_repository(settings) -> OrderPersistenceRepository | None:
    if not settings.postgres_enabled:
        return None
    try:
        postgres_client = PostgresClient(settings=settings)
        postgres_client.connect()
        repository = OrderPersistenceRepository(postgres_client=postgres_client)
        repository.ensure_tables()
        return repository
    except Exception:
        return None


def build_execution_service() -> ExecutionService:
    settings = get_settings()
    persistence_repository = _build_persistence_repository(settings)

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
        persistence_repository=persistence_repository,
        update_consumer=_UPDATE_CONSUMER,
        position_service=_POSITION_SERVICE,
    )


def build_lifecycle_only_service() -> ExecutionService:
    settings = get_settings()
    persistence_repository = _build_persistence_repository(settings)
    return ExecutionService(
        settings=settings,
        signal_reader=None,
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=_LIFECYCLE_STORE,
        state_machine=_STATE_MACHINE,
        persistence_repository=persistence_repository,
        update_consumer=_UPDATE_CONSUMER,
        position_service=_POSITION_SERVICE,
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
    open_position_count = len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0])

    try:
        service = build_execution_service()
        status = service.get_status()
        replay_ready = status.replay_ready
        approved_loaded = status.approved_loaded
        active_order_count = status.active_order_count
        open_position_count = status.open_position_count
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
        "open_position_count": open_position_count,
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
            "open_position_count": status.open_position_count,
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
            "open_position_count": len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0]),
            "last_prepared_at": None,
            "message": f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})",
        }


@app.post("/execution-service/broker/place-test")
def place_test() -> dict[str, object]:
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        order_type="MARKET",
        product="INTRADAY",
        validity="DAY",
        correlation_id=f"manual-test-correlation-{datetime.utcnow().timestamp()}",
        idempotency_key=f"manual-test-idempotency-{datetime.utcnow().timestamp()}",
    )

    service = build_lifecycle_only_service()
    result = service.submit_order_request(
        request=request,
        submit_message="Manual test order submitted to broker adapter",
    )

    return {
        "order_id": result.order_id,
        "duplicate_of_order_id": result.duplicate_of_order_id,
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
    service = build_lifecycle_only_service()
    orders = service.list_order_lifecycle()
    return {
        "service": "execution_service",
        "count": len(orders),
        "orders": [order.model_dump(mode="json") for order in orders],
    }


@app.get("/execution-service/orders/{order_id}/history")
def order_history(order_id: str) -> dict[str, object]:
    service = build_lifecycle_only_service()
    try:
        history = service.get_order_history(order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}") from exc

    if not history:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}")

    return {
        "service": "execution_service",
        "order_id": order_id,
        "history_count": len(history),
        "history": [event.model_dump(mode="json") for event in history],
    }


@app.post("/execution-service/broker/consume-update")
def consume_broker_update(payload: dict[str, object]) -> dict[str, object]:
    service = build_lifecycle_only_service()
    try:
        event = service.consume_broker_update(payload, source="api")
    except UnknownBrokerUpdateOrderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (InvalidOrderTransition, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "service": "execution_service",
        "event": event.model_dump(mode="json"),
    }


@app.post("/execution-service/orders/{order_id}/cancel")
def cancel_order(order_id: str) -> dict[str, object]:
    service = build_lifecycle_only_service()
    try:
        result = service.cancel_order(order_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}") from exc
    except OrderActionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (InvalidOrderTransition, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "order_id": result.order_id,
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


@app.post("/execution-service/orders/{order_id}/modify")
def modify_order(order_id: str, payload: dict[str, object]) -> dict[str, object]:
    service = build_lifecycle_only_service()
    try:
        result = service.modify_order(
            order_id,
            quantity=payload.get("quantity"),
            limit_price=payload.get("limit_price"),
            stop_price=payload.get("stop_price"),
            order_type=payload.get("order_type"),
            validity=payload.get("validity"),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}") from exc
    except OrderActionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (InvalidOrderTransition, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "order_id": result.order_id,
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


@app.get("/execution-service/positions")
def list_positions() -> dict[str, object]:
    service = build_lifecycle_only_service()
    positions = service.list_positions()
    return {
        "service": "execution_service",
        "count": len(positions),
        "positions": [
            PositionView(
                symbol=p.symbol,
                net_quantity=p.net_quantity,
                avg_price=p.avg_price,
                side=p.side,
                realized_pnl=p.realized_pnl,
                open_lots=[PositionLotView(quantity=l.quantity, price=l.price, side=l.side) for l in p.open_lots],
                updated_at=p.updated_at,
            ).model_dump(mode="json")
            for p in positions
        ],
    }


@app.get("/execution-service/positions/{symbol}")
def get_position(symbol: str) -> dict[str, object]:
    service = build_lifecycle_only_service()
    p = service.get_position(symbol)
    return {
        "service": "execution_service",
        "position": PositionView(
            symbol=p.symbol,
            net_quantity=p.net_quantity,
            avg_price=p.avg_price,
            side=p.side,
            realized_pnl=p.realized_pnl,
            open_lots=[PositionLotView(quantity=l.quantity, price=l.price, side=l.side) for l in p.open_lots],
            updated_at=p.updated_at,
        ).model_dump(mode="json"),
    }
PY

cat > "$ROOT/tests/unit/test_execution_service.py" <<'PY'
from datetime import UTC, datetime

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import BrokerPlaceOrderRequest
from services.execution_service.app.order_state_machine import OrderStateMachine, OrderStatus
from services.execution_service.app.positions import FillEvent, PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.update_consumer import BrokerUpdateConsumer
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


def build_service() -> ExecutionService:
    settings = build_settings("fyers_stub")
    return ExecutionService(
        settings=settings,
        signal_reader=None,
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings),
        lifecycle_store=InMemoryOrderLifecycleStore(),
        state_machine=OrderStateMachine(),
        update_consumer=BrokerUpdateConsumer(),
        position_service=PositionService(),
    )


def create_and_fill_buy_order(service: ExecutionService, qty: int = 1, price: float = 600.25) -> str:
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=qty,
        correlation_id=f"corr-{datetime.now(UTC).timestamp()}",
        idempotency_key=f"idem-{datetime.now(UTC).timestamp()}",
    )
    result = service.submit_order_request(request, "submit")
    assert result.order_id is not None
    service.consume_broker_update(
        {"order_id": result.order_id, "status": "OPEN"},
        source="test",
    )
    service.consume_broker_update(
        {"order_id": result.order_id, "status": "COMPLETE", "filledQty": qty, "avgPrice": price},
        source="test",
    )
    return result.order_id


def test_position_service_buy_fill_creates_long_position() -> None:
    ps = PositionService()
    snapshot = ps.apply_fill(
        FillEvent(
            order_id="ord-1",
            symbol="NSE:SBIN-EQ",
            fill_quantity=2,
            fill_price=600.0,
            side="BUY",
            event_time=datetime.now(UTC),
        )
    )
    assert snapshot.net_quantity == 2
    assert snapshot.side == "LONG"
    assert snapshot.avg_price == 600.0
    assert snapshot.realized_pnl == 0.0


def test_position_service_sell_against_long_realizes_pnl() -> None:
    ps = PositionService()
    ps.apply_fill(FillEvent(order_id="ord-1", symbol="NSE:SBIN-EQ", fill_quantity=2, fill_price=600.0, side="BUY", event_time=datetime.now(UTC)))
    snapshot = ps.apply_fill(FillEvent(order_id="ord-2", symbol="NSE:SBIN-EQ", fill_quantity=1, fill_price=610.0, side="SELL", event_time=datetime.now(UTC)))
    assert snapshot.net_quantity == 1
    assert snapshot.realized_pnl == 10.0


def test_execution_service_updates_position_on_fill() -> None:
    service = build_service()
    create_and_fill_buy_order(service, qty=1, price=600.25)
    position = service.get_position("NSE:SBIN-EQ")
    assert position.net_quantity == 1
    assert position.side == "LONG"
    assert position.avg_price == 600.25


def test_execution_service_flips_to_flat_after_round_trip() -> None:
    service = build_service()
    create_and_fill_buy_order(service, qty=1, price=600.0)

    sell_request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="SELL",
        quantity=1,
        correlation_id=f"sell-corr-{datetime.now(UTC).timestamp()}",
        idempotency_key=f"sell-idem-{datetime.now(UTC).timestamp()}",
    )
    sell_result = service.submit_order_request(sell_request, "sell submit")
    assert sell_result.order_id is not None
    service.consume_broker_update({"order_id": sell_result.order_id, "status": "OPEN"}, source="test")
    service.consume_broker_update(
        {"order_id": sell_result.order_id, "status": "COMPLETE", "filledQty": 1, "avgPrice": 610.0},
        source="test",
    )

    position = service.get_position("NSE:SBIN-EQ")
    assert position.net_quantity == 0
    assert position.side == "FLAT"
    assert position.realized_pnl == 10.0


def test_execution_service_status_reports_open_position_count() -> None:
    service = build_service()
    create_and_fill_buy_order(service, qty=1, price=600.0)
    status = service.get_status()
    assert status.open_position_count == 1
PY

cat > "$ROOT/tests/unit/test_execution_service_api.py" <<'PY'
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def __init__(self) -> None:
        self._position = {
            "symbol": "NSE:SBIN-EQ",
            "net_quantity": 1,
            "avg_price": 600.25,
            "side": "LONG",
            "realized_pnl": 0.0,
            "open_lots": [{"quantity": 1, "price": 600.25, "side": "BUY"}],
            "updated_at": datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
        }

    def list_positions(self):
        class P:
            pass
        p = P()
        p.symbol = self._position["symbol"]
        p.net_quantity = self._position["net_quantity"]
        p.avg_price = self._position["avg_price"]
        p.side = self._position["side"]
        p.realized_pnl = self._position["realized_pnl"]
        p.open_lots = [type("Lot", (), lot)() for lot in self._position["open_lots"]]
        p.updated_at = self._position["updated_at"]
        return [p]

    def get_position(self, symbol: str):
        class P:
            pass
        p = P()
        p.symbol = self._position["symbol"]
        p.net_quantity = self._position["net_quantity"]
        p.avg_price = self._position["avg_price"]
        p.side = self._position["side"]
        p.realized_pnl = self._position["realized_pnl"]
        p.open_lots = [type("Lot", (), lot)() for lot in self._position["open_lots"]]
        p.updated_at = self._position["updated_at"]
        return p


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_positions_endpoint() -> None:
    response = client.get("/execution-service/positions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["positions"][0]["symbol"] == "NSE:SBIN-EQ"
    assert body["positions"][0]["net_quantity"] == 1


def test_single_position_endpoint() -> None:
    response = client.get("/execution-service/positions/NSE:SBIN-EQ")
    assert response.status_code == 200
    body = response.json()
    assert body["position"]["symbol"] == "NSE:SBIN-EQ"
    assert body["position"]["side"] == "LONG"
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
marker = "# Item 30 — Position service skeleton"
if marker not in text:
    addition = """

# Item 30 — Position service skeleton
## Checklist

  * Add position service module
  * Add fill event model
  * Add long and short lot tracking
  * Add net quantity calculation
  * Add average price calculation
  * Add realized pnl calculation skeleton
  * Update execution service on filled events
  * Add list positions service method
  * Add get position service method
  * Add positions API endpoint
  * Add single position API endpoint
  * Add tests for long position creation
  * Add tests for round-trip pnl
  * Add tests for service position updates
  * Verify tests pass
  * Verify runtime position endpoint
  * Docs updated

## Definition of done

  * Code written
  * Position service added
  * Fill processing added
  * Position APIs added
  * Tests added
  * Runtime path verified
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 30 patch applied"
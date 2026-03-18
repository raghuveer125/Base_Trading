#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app"
mkdir -p "$ROOT/tests/unit"

cat > "$ROOT/services/execution_service/app/audit.py" <<'PY'
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
PY

cat > "$ROOT/services/execution_service/app/audit_persistence.py" <<'PY'
from __future__ import annotations

import json
from services.execution_service.app.audit import AuditEvent
from shared.postgres.client import PostgresClient


class AuditPersistenceRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client

    def ensure_tables(self) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_audit_events (
                    audit_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL,
                    order_id TEXT,
                    symbol TEXT,
                    actor TEXT NOT NULL,
                    metadata JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_audit_events_order_id_event_time
                ON execution_audit_events (order_id, event_time)
                """
            )
        self._postgres_client.commit()

    def append(self, event: AuditEvent) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_audit_events (
                    audit_id,
                    event_type,
                    message,
                    event_time,
                    order_id,
                    symbol,
                    actor,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    event.audit_id,
                    event.event_type,
                    event.message,
                    event.event_time,
                    event.order_id,
                    event.symbol,
                    event.actor,
                    json.dumps(event.metadata) if event.metadata is not None else None,
                ),
            )
        self._postgres_client.commit()

    def list_events(self, *, order_id: str | None = None, limit: int | None = None) -> list[AuditEvent]:
        query = """
            SELECT audit_id, event_type, message, event_time, order_id, symbol, actor, metadata
            FROM execution_audit_events
        """
        params: list[object] = []
        if order_id is not None:
            query += " WHERE order_id = %s"
            params.append(order_id)
        query += " ORDER BY event_time ASC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self._postgres_client.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        return [
            AuditEvent(
                audit_id=row[0],
                event_type=row[1],
                message=row[2],
                event_time=row[3],
                order_id=row[4],
                symbol=row[5],
                actor=row[6],
                metadata=row[7],
            )
            for row in rows
        ]
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


class PortfolioView(BaseModel):
    open_position_count: int
    gross_quantity: int
    net_quantity: int
    realized_pnl: float
    long_position_count: int
    short_position_count: int
    symbols: list[str]
    updated_at: datetime


class ExecutionRiskView(BaseModel):
    allowed: bool
    reason: str
    code: str
    symbol: str
    side: str
    quantity: int
    max_order_quantity: int
    max_symbol_position_quantity: int
    max_open_positions: int


class AuditEventView(BaseModel):
    audit_id: str
    event_type: str
    message: str
    event_time: datetime
    order_id: str | None = None
    symbol: str | None = None
    actor: str
    metadata: dict[str, Any] | None = None


class AuditNoteRequest(BaseModel):
    message: str
    order_id: str | None = None
    symbol: str | None = None
    actor: str = "operator"
    metadata: dict[str, Any] | None = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message is required")
        return value


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

from services.execution_service.app.audit import AuditEvent, InMemoryAuditTrail
from services.execution_service.app.audit_persistence import AuditPersistenceRepository
from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.execution_risk import ExecutionRiskDecision, ExecutionRiskGuard
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import (
    AuditNoteRequest,
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
from services.execution_service.app.portfolio import PortfolioService
from services.execution_service.app.position_persistence import PositionPersistenceRepository
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


class ExecutionRiskRejectedError(ValueError):
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
        portfolio_service: PortfolioService | None = None,
        position_persistence_repository: PositionPersistenceRepository | None = None,
        execution_risk_guard: ExecutionRiskGuard | None = None,
        audit_trail: InMemoryAuditTrail | None = None,
        audit_persistence_repository: AuditPersistenceRepository | None = None,
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
        self._portfolio_service = portfolio_service or PortfolioService()
        self._position_persistence_repository = position_persistence_repository
        self._execution_risk_guard = execution_risk_guard or ExecutionRiskGuard(
            max_order_quantity=settings.risk_max_signal_size,
            max_symbol_position_quantity=settings.risk_max_signal_size,
            max_open_positions=settings.risk_max_open_positions,
        )
        self._audit_trail = audit_trail or InMemoryAuditTrail()
        self._audit_persistence_repository = audit_persistence_repository
        self._orders_prepared = 0
        self._last_prepared_at: datetime | None = None

    @property
    def execution_risk_limits(self) -> dict[str, int]:
        return {
            "max_order_quantity": self._execution_risk_guard._max_order_quantity,
            "max_symbol_position_quantity": self._execution_risk_guard._max_symbol_position_quantity,
            "max_open_positions": self._execution_risk_guard._max_open_positions,
        }

    def _append_audit_event(
        self,
        *,
        event_type: str,
        message: str,
        order_id: str | None = None,
        symbol: str | None = None,
        actor: str = "system",
        metadata: dict | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            audit_id=f"audit-{uuid4().hex[:12]}",
            event_type=event_type,
            message=message,
            event_time=datetime.now(UTC),
            order_id=order_id,
            symbol=symbol,
            actor=actor,
            metadata=metadata,
        )
        self._audit_trail.append(event)
        if self._audit_persistence_repository is not None:
            self._audit_persistence_repository.append(event)
        return event

    def add_operator_note(self, request: AuditNoteRequest):
        return self._append_audit_event(
            event_type="operator_note",
            message=request.message,
            order_id=request.order_id,
            symbol=request.symbol,
            actor=request.actor,
            metadata=request.metadata,
        )

    def list_audit_events(self, *, order_id: str | None = None, limit: int | None = None):
        events = self._audit_trail.list_events(order_id=order_id, limit=limit)
        if self._audit_persistence_repository is not None:
            persisted = self._audit_persistence_repository.list_events(order_id=order_id, limit=limit)
            if persisted:
                return persisted
        return events

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

    def _persist_position_snapshot(self, symbol: str) -> None:
        if self._position_persistence_repository is None:
            return
        snapshot = self._position_service.get_position(symbol)
        self._position_persistence_repository.upsert_position(snapshot)

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

    def evaluate_execution_risk(self, request: BrokerPlaceOrderRequest) -> ExecutionRiskDecision:
        positions = self.list_positions()
        return self._execution_risk_guard.evaluate_order(
            request=request,
            positions=positions,
        )

    def _build_duplicate_response(
        self,
        *,
        request: BrokerPlaceOrderRequest,
        order_id: str,
    ) -> BrokerPlaceOrderResponse:
        self._append_audit_event(
            event_type="duplicate_submission",
            message=f"Duplicate idempotency key detected; reusing order {order_id}",
            order_id=order_id,
            symbol=request.symbol,
            actor="system",
            metadata={"idempotency_key": request.idempotency_key},
        )
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

        risk_decision = self.evaluate_execution_risk(request)
        if not risk_decision.allowed:
            self._append_audit_event(
                event_type="risk_rejected",
                message=risk_decision.reason,
                order_id=None,
                symbol=request.symbol,
                actor="system",
                metadata={"code": risk_decision.code, "side": request.side, "quantity": request.quantity},
            )
            raise ExecutionRiskRejectedError(risk_decision.reason)

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
        self._append_audit_event(
            event_type="order_created",
            message=submit_message,
            order_id=internal_order_id,
            symbol=request.symbol,
            actor="system",
            metadata={"side": request.side, "quantity": request.quantity},
        )

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
            self._append_audit_event(
                event_type="broker_ack",
                message=result.message,
                order_id=internal_order_id,
                symbol=request.symbol,
                actor="system",
                metadata={"external_order_id": result.external_order_id},
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
            self._persist_event(internal_order_id)
            self._append_audit_event(
                event_type="broker_reject",
                message=result.message,
                order_id=internal_order_id,
                symbol=request.symbol,
                actor="system",
                metadata={"external_order_id": result.external_order_id},
            )

        result.order_id = internal_order_id
        return result

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
        self._append_audit_event(
            event_type="cancel_requested",
            message="Cancel requested",
            order_id=order_id,
            symbol=stored.symbol,
            actor="system",
        )

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
        self._append_audit_event(
            event_type=event_type,
            message=result.message,
            order_id=order_id,
            symbol=stored.symbol,
            actor="system",
        )
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
        self._append_audit_event(
            event_type=event.event_type,
            message=result.message,
            order_id=order_id,
            symbol=stored.symbol,
            actor="system",
            metadata=result.raw_response,
        )
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
        self._append_audit_event(
            event_type="broker_update",
            message=event.message or f"Broker update mapped from {broker_status}",
            order_id=order_id,
            symbol=stored.symbol,
            actor="system",
            metadata=raw_payload,
        )

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
                self._persist_position_snapshot(stored.symbol)
                self._append_audit_event(
                    event_type="position_updated",
                    message=f"Position updated for {stored.symbol}",
                    order_id=order_id,
                    symbol=stored.symbol,
                    actor="system",
                    metadata={"filled_quantity": filled_quantity, "avg_price": avg_price},
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
        if self._position_persistence_repository is not None:
            persisted = self._position_persistence_repository.get_position(symbol)
            if persisted is not None:
                return persisted
        return self._position_service.get_position(symbol)

    def list_positions(self):
        if self._position_persistence_repository is not None:
            persisted = self._position_persistence_repository.list_positions()
            if persisted:
                return persisted
        return self._position_service.list_positions()

    def get_portfolio(self):
        return self._portfolio_service.build_snapshot(self.list_positions())

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
        open_position_count = len([p for p in self.list_positions() if p.net_quantity != 0])
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
from datetime import datetime
from fastapi import FastAPI, HTTPException

from services.execution_service.app.audit import InMemoryAuditTrail
from services.execution_service.app.audit_persistence import AuditPersistenceRepository
from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.execution_risk import ExecutionRiskGuard
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import (
    AuditEventView,
    AuditNoteRequest,
    BrokerPlaceOrderRequest,
    BrokerPlaceOrderResponse,
    ExecutionRiskView,
    PortfolioView,
    PositionLotView,
    PositionView,
)
from services.execution_service.app.order_state_machine import InvalidOrderTransition, OrderStateMachine
from services.execution_service.app.persistence import OrderPersistenceRepository
from services.execution_service.app.portfolio import PortfolioService
from services.execution_service.app.position_persistence import PositionPersistenceRepository
from services.execution_service.app.positions import PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import (
    ExecutionRiskRejectedError,
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
_PORTFOLIO_SERVICE = PortfolioService()
_AUDIT_TRAIL = InMemoryAuditTrail()


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


def _build_position_persistence_repository(settings) -> PositionPersistenceRepository | None:
    if not settings.postgres_enabled:
        return None
    try:
        postgres_client = PostgresClient(settings=settings)
        postgres_client.connect()
        repository = PositionPersistenceRepository(postgres_client=postgres_client)
        repository.ensure_tables()
        return repository
    except Exception:
        return None


def _build_audit_persistence_repository(settings) -> AuditPersistenceRepository | None:
    if not settings.postgres_enabled:
        return None
    try:
        postgres_client = PostgresClient(settings=settings)
        postgres_client.connect()
        repository = AuditPersistenceRepository(postgres_client=postgres_client)
        repository.ensure_tables()
        return repository
    except Exception:
        return None


def _build_execution_risk_guard(settings) -> ExecutionRiskGuard:
    return ExecutionRiskGuard(
        max_order_quantity=settings.risk_max_signal_size,
        max_symbol_position_quantity=settings.risk_max_signal_size,
        max_open_positions=settings.risk_max_open_positions,
    )


def build_execution_service() -> ExecutionService:
    settings = get_settings()
    persistence_repository = _build_persistence_repository(settings)
    position_persistence_repository = _build_position_persistence_repository(settings)
    audit_persistence_repository = _build_audit_persistence_repository(settings)
    execution_risk_guard = _build_execution_risk_guard(settings)

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
        portfolio_service=_PORTFOLIO_SERVICE,
        position_persistence_repository=position_persistence_repository,
        execution_risk_guard=execution_risk_guard,
        audit_trail=_AUDIT_TRAIL,
        audit_persistence_repository=audit_persistence_repository,
    )


def build_lifecycle_only_service() -> ExecutionService:
    settings = get_settings()
    persistence_repository = _build_persistence_repository(settings)
    position_persistence_repository = _build_position_persistence_repository(settings)
    audit_persistence_repository = _build_audit_persistence_repository(settings)
    execution_risk_guard = _build_execution_risk_guard(settings)
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
        portfolio_service=_PORTFOLIO_SERVICE,
        position_persistence_repository=position_persistence_repository,
        execution_risk_guard=execution_risk_guard,
        audit_trail=_AUDIT_TRAIL,
        audit_persistence_repository=audit_persistence_repository,
    )


@app.post("/execution-service/risk/check")
def execution_risk_check(payload: dict[str, object]) -> dict[str, object]:
    service = build_lifecycle_only_service()
    request = BrokerPlaceOrderRequest(
        symbol=str(payload.get("symbol")),
        side=str(payload.get("side")),
        quantity=int(payload.get("quantity")),
        order_type=str(payload.get("order_type", "MARKET")),
        product=str(payload.get("product", "INTRADAY")),
        validity=str(payload.get("validity", "DAY")),
        limit_price=float(payload.get("limit_price", 0.0)),
        stop_price=float(payload.get("stop_price", 0.0)),
        disclosed_qty=int(payload.get("disclosed_qty", 0)),
        offline_order=bool(payload.get("offline_order", False)),
        stop_loss=float(payload.get("stop_loss", 0.0)),
        take_profit=float(payload.get("take_profit", 0.0)),
        correlation_id=payload.get("correlation_id"),
        idempotency_key=payload.get("idempotency_key"),
    )
    decision = service.evaluate_execution_risk(request)
    limits = service.execution_risk_limits
    return {
        "service": "execution_service",
        "risk": ExecutionRiskView(
            allowed=decision.allowed,
            reason=decision.reason,
            code=decision.code,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            max_order_quantity=limits["max_order_quantity"],
            max_symbol_position_quantity=limits["max_symbol_position_quantity"],
            max_open_positions=limits["max_open_positions"],
        ).model_dump(mode="json"),
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
    try:
        result = service.submit_order_request(
            request=request,
            submit_message="Manual test order submitted to broker adapter",
        )
    except ExecutionRiskRejectedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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


@app.get("/execution-service/portfolio")
def get_portfolio() -> dict[str, object]:
    service = build_lifecycle_only_service()
    p = service.get_portfolio()
    return {
        "service": "execution_service",
        "portfolio": PortfolioView(
            open_position_count=p.open_position_count,
            gross_quantity=p.gross_quantity,
            net_quantity=p.net_quantity,
            realized_pnl=p.realized_pnl,
            long_position_count=p.long_position_count,
            short_position_count=p.short_position_count,
            symbols=p.symbols,
            updated_at=p.updated_at,
        ).model_dump(mode="json"),
    }


@app.post("/execution-service/audit/note")
def add_audit_note(payload: dict[str, object]) -> dict[str, object]:
    service = build_lifecycle_only_service()
    request = AuditNoteRequest(
        message=str(payload.get("message", "")),
        order_id=payload.get("order_id"),
        symbol=payload.get("symbol"),
        actor=str(payload.get("actor", "operator")),
        metadata=payload.get("metadata"),
    )
    event = service.add_operator_note(request)
    return {
        "service": "execution_service",
        "event": AuditEventView(
            audit_id=event.audit_id,
            event_type=event.event_type,
            message=event.message,
            event_time=event.event_time,
            order_id=event.order_id,
            symbol=event.symbol,
            actor=event.actor,
            metadata=event.metadata,
        ).model_dump(mode="json"),
    }


@app.get("/execution-service/audit")
def list_audit_events(order_id: str | None = None, limit: int | None = None) -> dict[str, object]:
    service = build_lifecycle_only_service()
    events = service.list_audit_events(order_id=order_id, limit=limit)
    return {
        "service": "execution_service",
        "count": len(events),
        "events": [
            AuditEventView(
                audit_id=e.audit_id,
                event_type=e.event_type,
                message=e.message,
                event_time=e.event_time,
                order_id=e.order_id,
                symbol=e.symbol,
                actor=e.actor,
                metadata=e.metadata,
            ).model_dump(mode="json")
            for e in events
        ],
    }
PY

cat > "$ROOT/tests/unit/test_execution_service.py" <<'PY'
from datetime import UTC, datetime

from services.execution_service.app.audit import InMemoryAuditTrail
from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.execution_risk import ExecutionRiskGuard
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import AuditNoteRequest, BrokerPlaceOrderRequest
from services.execution_service.app.order_state_machine import OrderStateMachine
from services.execution_service.app.portfolio import PortfolioService
from services.execution_service.app.positions import PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionRiskRejectedError, ExecutionService
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
        portfolio_service=PortfolioService(),
        execution_risk_guard=ExecutionRiskGuard(
            max_order_quantity=1,
            max_symbol_position_quantity=1,
            max_open_positions=5,
        ),
        audit_trail=InMemoryAuditTrail(),
    )


def create_order(service: ExecutionService) -> str:
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id=f"corr-{datetime.now(UTC).timestamp()}",
        idempotency_key=f"idem-{datetime.now(UTC).timestamp()}",
    )
    result = service.submit_order_request(request, "submit")
    assert result.order_id is not None
    return result.order_id


def test_operator_note_is_recorded() -> None:
    service = build_service()
    event = service.add_operator_note(
        AuditNoteRequest(
            message="Checked broker heartbeat before market open",
            symbol="NSE:SBIN-EQ",
            actor="operator",
        )
    )
    assert event.event_type == "operator_note"
    events = service.list_audit_events()
    assert len(events) == 1
    assert events[0].message == "Checked broker heartbeat before market open"


def test_order_submission_creates_audit_events() -> None:
    service = build_service()
    order_id = create_order(service)
    events = service.list_audit_events(order_id=order_id)
    assert len(events) >= 2
    event_types = [e.event_type for e in events]
    assert "order_created" in event_types
    assert "broker_ack" in event_types


def test_broker_update_creates_audit_event() -> None:
    service = build_service()
    order_id = create_order(service)
    service.consume_broker_update({"order_id": order_id, "status": "OPEN"}, source="test")
    events = service.list_audit_events(order_id=order_id)
    assert any(e.event_type == "broker_update" for e in events)


def test_risk_rejection_creates_audit_event() -> None:
    service = build_service()
    service._execution_risk_guard = ExecutionRiskGuard(
        max_order_quantity=1,
        max_symbol_position_quantity=1,
        max_open_positions=0,
    )
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id="risk-test",
        idempotency_key="risk-test",
    )
    try:
        service.submit_order_request(request, "submit")
    except ExecutionRiskRejectedError:
        pass
    else:
        raise AssertionError("Expected ExecutionRiskRejectedError")

    events = service.list_audit_events()
    assert any(e.event_type == "risk_rejected" for e in events)
PY

cat > "$ROOT/tests/unit/test_execution_service_api.py" <<'PY'
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def add_operator_note(self, request):
        class E:
            audit_id = "audit-123"
            event_type = "operator_note"
            message = request.message
            event_time = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
            order_id = request.order_id
            symbol = request.symbol
            actor = request.actor
            metadata = request.metadata
        return E()

    def list_audit_events(self, order_id=None, limit=None):
        class E:
            audit_id = "audit-123"
            event_type = "operator_note"
            message = "Manual note"
            event_time = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
            order_id = order_id
            symbol = "NSE:SBIN-EQ"
            actor = "operator"
            metadata = {"tag": "manual"}
        return [E()]


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_add_audit_note_endpoint() -> None:
    response = client.post(
        "/execution-service/audit/note",
        json={"message": "Manual note", "symbol": "NSE:SBIN-EQ", "actor": "operator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_type"] == "operator_note"
    assert body["event"]["message"] == "Manual note"


def test_list_audit_events_endpoint() -> None:
    response = client.get("/execution-service/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "operator_note"
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
marker = "# Item 34 — Execution audit trail and operator notes"
if marker not in text:
    addition = """

# Item 34 — Execution audit trail and operator notes
## Checklist

  * Add in-memory audit trail
  * Add audit persistence repository
  * Add audit event model
  * Record audit events for order creation and broker ack
  * Record audit events for risk rejection
  * Record audit events for broker updates and position updates
  * Add operator note request model
  * Add API endpoint to add audit note
  * Add API endpoint to list audit events
  * Add tests for operator notes
  * Add tests for order audit records
  * Add tests for broker update audit records
  * Verify tests pass
  * Verify runtime audit endpoints
  * Docs updated

## Definition of done

  * Code written
  * Audit trail added
  * Operator note support added
  * API added
  * Tests added
  * Runtime path verified
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 34 patch applied"

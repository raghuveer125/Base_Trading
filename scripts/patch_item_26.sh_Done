#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app"
mkdir -p "$ROOT/tests/unit"

cat > "$ROOT/services/execution_service/app/persistence.py" <<'PY'
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from services.execution_service.app.models import OrderEventView, OrderLifecycleView
from services.execution_service.app.order_state_machine import OrderEvent, OrderStatus
from shared.postgres.client import PostgresClient


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class PersistedOrder:
    order_id: str
    symbol: str
    side: str
    quantity: int
    broker: str
    current_status: str
    external_order_id: str | None
    correlation_id: str | None
    idempotency_key: str | None
    latest_message: str | None
    last_updated_at: datetime | None


class OrderPersistenceRepository:
    def __init__(self, postgres_client: PostgresClient) -> None:
        self._postgres_client = postgres_client

    def ensure_tables(self) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_orders (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    broker TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    external_order_id TEXT,
                    correlation_id TEXT,
                    idempotency_key TEXT,
                    latest_message TEXT,
                    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_orders_external_order_id
                ON execution_orders (external_order_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_orders_correlation_id
                ON execution_orders (correlation_id)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_orders_idempotency_key
                ON execution_orders (idempotency_key)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_order_events (
                    id BIGSERIAL PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time TIMESTAMPTZ NOT NULL,
                    message TEXT,
                    filled_quantity INTEGER NOT NULL DEFAULT 0,
                    remaining_quantity INTEGER,
                    average_price DOUBLE PRECISION,
                    raw_payload JSONB,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_execution_order_events_order_id_event_time
                ON execution_order_events (order_id, event_time)
                """
            )
        self._postgres_client.commit()

    def upsert_order(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        broker: str,
        current_status: OrderStatus,
        external_order_id: str | None,
        correlation_id: str | None,
        idempotency_key: str | None,
        latest_message: str | None,
        last_updated_at: datetime | None,
    ) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_orders (
                    order_id,
                    symbol,
                    side,
                    quantity,
                    broker,
                    current_status,
                    external_order_id,
                    correlation_id,
                    idempotency_key,
                    latest_message,
                    last_updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (order_id) DO UPDATE
                SET
                    symbol = EXCLUDED.symbol,
                    side = EXCLUDED.side,
                    quantity = EXCLUDED.quantity,
                    broker = EXCLUDED.broker,
                    current_status = EXCLUDED.current_status,
                    external_order_id = EXCLUDED.external_order_id,
                    correlation_id = EXCLUDED.correlation_id,
                    idempotency_key = EXCLUDED.idempotency_key,
                    latest_message = EXCLUDED.latest_message,
                    last_updated_at = EXCLUDED.last_updated_at
                """,
                (
                    order_id,
                    symbol,
                    side,
                    quantity,
                    broker,
                    current_status.value,
                    external_order_id,
                    correlation_id,
                    idempotency_key,
                    latest_message,
                    last_updated_at or utc_now(),
                ),
            )
        self._postgres_client.commit()

    def insert_event(self, event: OrderEvent) -> None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                INSERT INTO execution_order_events (
                    order_id,
                    from_status,
                    to_status,
                    event_type,
                    event_time,
                    message,
                    filled_quantity,
                    remaining_quantity,
                    average_price,
                    raw_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    event.order_id,
                    event.from_status.value,
                    event.to_status.value,
                    event.event_type,
                    event.event_time,
                    event.message,
                    event.filled_quantity,
                    event.remaining_quantity,
                    event.average_price,
                    json.dumps(event.raw_payload) if event.raw_payload is not None else None,
                ),
            )
        self._postgres_client.commit()

    def get_order(self, order_id: str) -> PersistedOrder | None:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    order_id,
                    symbol,
                    side,
                    quantity,
                    broker,
                    current_status,
                    external_order_id,
                    correlation_id,
                    idempotency_key,
                    latest_message,
                    last_updated_at
                FROM execution_orders
                WHERE order_id = %s
                """,
                (order_id,),
            )
            row = cur.fetchone()

        if row is None:
            return None

        return PersistedOrder(
            order_id=row[0],
            symbol=row[1],
            side=row[2],
            quantity=row[3],
            broker=row[4],
            current_status=row[5],
            external_order_id=row[6],
            correlation_id=row[7],
            idempotency_key=row[8],
            latest_message=row[9],
            last_updated_at=row[10],
        )

    def list_orders(self) -> list[OrderLifecycleView]:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    eo.order_id,
                    eo.symbol,
                    eo.side,
                    eo.quantity,
                    eo.broker,
                    eo.current_status,
                    eo.external_order_id,
                    eo.correlation_id,
                    eo.idempotency_key,
                    eo.latest_message,
                    eo.last_updated_at,
                    COUNT(eoe.id) AS history_count
                FROM execution_orders eo
                LEFT JOIN execution_order_events eoe
                    ON eo.order_id = eoe.order_id
                GROUP BY
                    eo.order_id,
                    eo.symbol,
                    eo.side,
                    eo.quantity,
                    eo.broker,
                    eo.current_status,
                    eo.external_order_id,
                    eo.correlation_id,
                    eo.idempotency_key,
                    eo.latest_message,
                    eo.last_updated_at
                ORDER BY eo.last_updated_at DESC NULLS LAST, eo.order_id DESC
                """
            )
            rows = cur.fetchall()

        result: list[OrderLifecycleView] = []
        for row in rows:
            result.append(
                OrderLifecycleView(
                    order_id=row[0],
                    symbol=row[1],
                    side=row[2],
                    quantity=row[3],
                    broker=row[4],
                    current_status=OrderStatus(row[5]),
                    history_count=int(row[10]),
                    external_order_id=row[6],
                    correlation_id=row[7],
                    idempotency_key=row[8],
                    latest_message=row[9],
                    last_updated_at=row[10 - 1],
                )
            )
        return result

    def get_history(self, order_id: str) -> list[OrderEventView]:
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT
                    order_id,
                    from_status,
                    to_status,
                    event_type,
                    event_time,
                    message,
                    filled_quantity,
                    remaining_quantity,
                    average_price,
                    raw_payload
                FROM execution_order_events
                WHERE order_id = %s
                ORDER BY event_time ASC, id ASC
                """,
                (order_id,),
            )
            rows = cur.fetchall()

        history: list[OrderEventView] = []
        for row in rows:
            history.append(
                OrderEventView(
                    order_id=row[0],
                    from_status=OrderStatus(row[1]),
                    to_status=OrderStatus(row[2]),
                    event_type=row[3],
                    event_time=row[4],
                    message=row[5],
                    filled_quantity=row[6],
                    remaining_quantity=row[7],
                    average_price=row[8],
                    raw_payload=row[9],
                )
            )
        return history

    def active_order_count(self) -> int:
        terminal_values = (
            OrderStatus.FILLED.value,
            OrderStatus.CANCELLED.value,
            OrderStatus.REJECTED.value,
        )
        with self._postgres_client.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM execution_orders
                WHERE current_status NOT IN (%s, %s, %s)
                """,
                terminal_values,
            )
            row = cur.fetchone()
        return int(row[0]) if row is not None else 0
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
from services.execution_service.app.persistence import OrderPersistenceRepository
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.signal_reader import ApprovedSignalReader
from shared.config.settings import Settings


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
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._broker_adapter = broker_adapter
        self._lifecycle_store = lifecycle_store or InMemoryOrderLifecycleStore()
        self._state_machine = state_machine or OrderStateMachine()
        self._persistence_repository = persistence_repository
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

    def register_manual_test_order(self, response: BrokerPlaceOrderResponse) -> str:
        symbol = "NSE:SBIN-EQ"
        side = "BUY"
        quantity = 1
        internal_order_id = self._build_internal_order_id(symbol, response.correlation_id or "manual-test")

        self._lifecycle_store.create_order(
            order_id=internal_order_id,
            symbol=symbol,
            side=side,
            quantity=quantity,
            broker=self._settings.execution_service_broker,
            correlation_id=response.correlation_id,
            idempotency_key=response.idempotency_key,
        )
        self._persist_current_order(internal_order_id)

        submitted_event = self._state_machine.transition(
            order_id=internal_order_id,
            current=OrderStatus.CREATED,
            target=OrderStatus.SUBMITTED,
            event_type="submit_request",
            message="Manual test order submitted to broker adapter",
        )
        self._lifecycle_store.append_event(internal_order_id, submitted_event)
        self._persist_event(internal_order_id)

        target = OrderStatus.ACKNOWLEDGED if response.accepted else (
            OrderStatus.REJECTED if response.status in {"rejected", "empty"} else OrderStatus.ERROR
        )
        event_type = "broker_ack" if response.accepted else "broker_reject"
        broker_event = self._state_machine.transition(
            order_id=internal_order_id,
            current=OrderStatus.SUBMITTED,
            target=target,
            event_type=event_type,
            message=response.message,
            raw_payload=response.raw_response,
        )
        self._lifecycle_store.append_event(
            internal_order_id,
            broker_event,
            external_order_id=response.external_order_id,
        )
        self._persist_event(internal_order_id)
        return internal_order_id

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
        self._persist_current_order(internal_order_id)

        created_event = self._state_machine.transition(
            order_id=internal_order_id,
            current=OrderStatus.CREATED,
            target=OrderStatus.SUBMITTED,
            event_type="submit_request",
            message="Order submitted to broker adapter",
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
        return self._lifecycle_store.get_history(order_id)[-1]

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
            last_prepared_at=self._last_prepared_at,
            message="Execution service ready",
        )
PY

cat > "$ROOT/services/execution_service/app/api.py" <<'PY'
from fastapi import FastAPI, HTTPException

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import BrokerPlaceOrderRequest, BrokerPlaceOrderResponse
from services.execution_service.app.order_state_machine import InvalidOrderTransition, OrderStateMachine, OrderStatus
from services.execution_service.app.persistence import OrderPersistenceRepository
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


def _build_persistence_repository(settings) -> OrderPersistenceRepository | None:
    if not settings.postgres_enabled:
        return None
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()
    repository = OrderPersistenceRepository(postgres_client=postgres_client)
    repository.ensure_tables()
    return repository


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

    service = build_lifecycle_only_service()
    order_id = service.register_manual_test_order(result)

    return {
        "order_id": order_id,
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
    history = service.get_order_history(order_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"Unknown order_id: {order_id}")
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

    service = build_lifecycle_only_service()
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
from services.execution_service.app.models import BrokerPlaceOrderRequest, BrokerPlaceOrderResponse
from services.execution_service.app.order_state_machine import (
    InvalidOrderTransition,
    OrderStateMachine,
    OrderStatus,
    normalize_broker_status,
)
from services.execution_service.app.persistence import OrderPersistenceRepository
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


class FakePersistenceRepository:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.events: list = []

    def upsert_order(
        self,
        *,
        order_id: str,
        symbol: str,
        side: str,
        quantity: int,
        broker: str,
        current_status,
        external_order_id,
        correlation_id,
        idempotency_key,
        latest_message,
        last_updated_at,
    ) -> None:
        self.orders[order_id] = {
            "order_id": order_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "broker": broker,
            "current_status": current_status.value,
            "external_order_id": external_order_id,
            "correlation_id": correlation_id,
            "idempotency_key": idempotency_key,
            "latest_message": latest_message,
            "last_updated_at": last_updated_at,
        }

    def insert_event(self, event) -> None:
        self.events.append(event)

    def list_orders(self):
        return []

    def get_history(self, order_id: str):
        return []

    def active_order_count(self) -> int:
        return len([o for o in self.orders.values() if o["current_status"] not in {"filled", "cancelled", "rejected"}])


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
    repo = FakePersistenceRepository()
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=store,
        state_machine=OrderStateMachine(),
        persistence_repository=repo,
    )
    result = service.place_first_prepared_order_once()
    orders = store.list_orders()

    assert result.accepted is True
    assert result.status == "accepted"
    assert result.external_order_id is not None
    assert result.idempotency_key is not None
    assert len(orders) == 1
    assert orders[0].current_status == OrderStatus.ACKNOWLEDGED
    assert orders[0].history_count == 2
    assert len(repo.events) == 2
    assert len(repo.orders) == 1


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
    repo = FakePersistenceRepository()
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=store,
        state_machine=OrderStateMachine(),
        persistence_repository=repo,
    )
    service.place_first_prepared_order_once()
    order = store.list_orders()[0]

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
    assert len(repo.events) == 4


def test_register_manual_test_order_persists_lifecycle() -> None:
    settings = build_settings("fyers_stub")
    store = InMemoryOrderLifecycleStore()
    repo = FakePersistenceRepository()
    service = ExecutionService(
        settings=settings,
        signal_reader=None,
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
        lifecycle_store=store,
        state_machine=OrderStateMachine(),
        persistence_repository=repo,
    )

    response = BrokerPlaceOrderResponse(
        broker="fyers_stub",
        adapter="fyers",
        accepted=True,
        status="accepted",
        external_order_id="ext-1",
        message="accepted",
        correlation_id="manual-test-correlation",
        idempotency_key="manual-test-idempotency",
        raw_response={"symbol": "NSE:SBIN-EQ"},
    )
    order_id = service.register_manual_test_order(response)

    assert order_id in repo.orders
    assert len(repo.events) == 2
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

    def register_manual_test_order(self, response: BrokerPlaceOrderResponse) -> str:
        return "ord-manual-test-api"

    def list_order_lifecycle(self):
        return []

    def get_order_history(self, order_id: str):
        return []


execution_api.build_execution_service = lambda: FakeExecutionService()
execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

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
    assert body["order_id"] == "ord-manual-test-api"


def test_order_listing_endpoint() -> None:
    response = client.get("/execution-service/orders")
    assert response.status_code == 200
    body = response.json()
    assert "orders" in body


def test_order_history_endpoint_404_when_missing() -> None:
    response = client.get("/execution-service/orders/ord-unknown/history")
    assert response.status_code == 404
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
marker = "# Item 26 — Order persistence in PostgreSQL"
if marker not in text:
    addition = """

# Item 26 — Order persistence in PostgreSQL
## Checklist

  * Add execution orders table
  * Add execution order events table
  * Add repository layer for orders and events
  * Persist order snapshot on lifecycle changes
  * Persist every lifecycle event
  * Add fetch order by id support
  * Add fetch order history support
  * Add list orders from persistence layer
  * Add active order count from persistence layer
  * Wire persistence into execution service
  * Keep in-memory lifecycle as hot runtime cache
  * Add persistence-aware service tests
  * Add API tests for persistence-backed endpoints
  * Verify tests pass
  * Verify manual test orders persist
  * Docs updated

## Definition of done

  * Code written
  * Tables added
  * Repository added
  * Persistence wired
  * Logs preserved
  * Tests added
  * Persistence path verified
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 26 patch applied"
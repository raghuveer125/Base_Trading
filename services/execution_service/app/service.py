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

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

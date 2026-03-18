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

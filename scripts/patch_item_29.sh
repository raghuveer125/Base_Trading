#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app"
mkdir -p "$ROOT/tests/unit"

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

cat > "$ROOT/services/execution_service/app/brokers/base.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.execution_service.app.models import (
    BrokerActionResponse,
    BrokerCancelOrderRequest,
    BrokerHealth,
    BrokerModifyOrderRequest,
    BrokerPlaceOrderRequest,
    BrokerPlaceOrderResponse,
)


class BrokerAdapter(Protocol):
    def adapter_name(self) -> str:
        ...

    def is_live(self) -> bool:
        ...

    def health_check(self) -> BrokerHealth:
        ...

    def place_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        ...

    def cancel_order(self, request: BrokerCancelOrderRequest) -> BrokerActionResponse:
        ...

    def modify_order(self, request: BrokerModifyOrderRequest) -> BrokerActionResponse:
        ...


@dataclass(slots=True)
class BrokerCapabilities:
    supports_live_orders: bool
    supports_modify: bool
    supports_cancel: bool
    supports_websocket_updates: bool
PY

cat > "$ROOT/services/execution_service/app/brokers/fyers_adapter.py" <<'PY'
from __future__ import annotations

from typing import Any

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.models import (
    BrokerActionResponse,
    BrokerCancelOrderRequest,
    BrokerHealth,
    BrokerModifyOrderRequest,
    BrokerPlaceOrderRequest,
    BrokerPlaceOrderResponse,
)
from shared.config.settings import Settings
from shared.logging.logger import get_logger


class FyersBrokerAdapter(BrokerAdapter):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("execution_service.brokers.fyers")

    def adapter_name(self) -> str:
        return self._settings.execution_service_broker

    def is_live(self) -> bool:
        return self._settings.execution_service_broker.strip().lower() == "fyers_live"

    def health_check(self) -> BrokerHealth:
        has_client_id = bool(self._settings.fyers_client_id.strip())
        has_access_token = bool(self._settings.fyers_access_token.strip())

        ready = has_client_id and has_access_token
        mode = "live" if self.is_live() else "stub"
        message = "FYERS broker adapter ready" if ready else "FYERS broker adapter missing credentials"

        self._logger.info(
            "broker_health_check",
            broker=self.adapter_name(),
            mode=mode,
            ready=ready,
            has_client_id=has_client_id,
            has_access_token=has_access_token,
        )

        return BrokerHealth(
            broker=self.adapter_name(),
            adapter="fyers",
            mode=mode,
            ready=ready,
            has_client_id=has_client_id,
            has_access_token=has_access_token,
            message=message,
        )

    def _map_side(self, side: str) -> int:
        return 1 if side.upper() == "BUY" else -1

    def _map_order_type(self, order_type: str) -> int:
        normalized = order_type.upper()
        mapping = {
            "LIMIT": 1,
            "MARKET": 2,
            "STOP": 3,
            "STOP_LIMIT": 4,
        }
        return mapping[normalized]

    def _build_payload(self, request: BrokerPlaceOrderRequest) -> dict[str, Any]:
        return {
            "symbol": request.symbol,
            "qty": request.quantity,
            "type": self._map_order_type(request.order_type),
            "side": self._map_side(request.side),
            "productType": request.product,
            "limitPrice": request.limit_price,
            "stopPrice": request.stop_price,
            "validity": request.validity,
            "disclosedQty": request.disclosed_qty,
            "offlineOrder": request.offline_order,
            "stopLoss": request.stop_loss,
            "takeProfit": request.take_profit,
            "orderTag": request.idempotency_key or request.correlation_id or "execution_service",
        }

    def _extract_order_id(self, response: dict[str, Any]) -> str | None:
        candidates = [
            response.get("id"),
            response.get("order_id"),
            response.get("orderId"),
        ]
        data = response.get("data")
        if isinstance(data, dict):
            candidates.extend(
                [
                    data.get("id"),
                    data.get("order_id"),
                    data.get("orderId"),
                ]
            )
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return None

    def _is_success_response(self, response: dict[str, Any]) -> bool:
        return bool(response.get("s") == "ok" or response.get("code") in {200, 201, 1101})

    def _get_live_client(self) -> Any:
        try:
            from fyers_apiv3 import fyersModel
        except Exception as exc:
            raise RuntimeError("fyers_apiv3 package is not installed") from exc

        token = f"{self._settings.fyers_client_id}:{self._settings.fyers_access_token}"
        return fyersModel.FyersModel(
            client_id=self._settings.fyers_client_id,
            is_async=False,
            token=token,
            log_path="",
        )

    def _place_live_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        payload = self._build_payload(request)
        client = self._get_live_client()
        raw_response = client.place_order(payload)
        if not isinstance(raw_response, dict):
            raw_response = {"raw": str(raw_response)}

        accepted = self._is_success_response(raw_response)
        external_order_id = self._extract_order_id(raw_response)
        status = "accepted" if accepted else "rejected"

        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=accepted,
            status=status,
            external_order_id=external_order_id,
            message=raw_response.get("message") or raw_response.get("msg") or "FYERS live order processed",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response=raw_response,
        )

    def place_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        health = self.health_check()
        if not health.ready:
            return BrokerPlaceOrderResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="rejected",
                external_order_id=None,
                message="Broker credentials missing",
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
            )

        if self.is_live():
            try:
                return self._place_live_order(request)
            except Exception as exc:
                self._logger.exception(
                    "fyers_live_order_submit_failed",
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                )
                return BrokerPlaceOrderResponse(
                    broker=self.adapter_name(),
                    adapter="fyers",
                    accepted=False,
                    status="error",
                    external_order_id=None,
                    message=f"FYERS live order failed: {exc.__class__.__name__}: {exc}",
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                )

        synthetic_id = (
            f"stub-{request.symbol.replace(':', '_')}-"
            f"{request.side.lower()}-{request.quantity}-"
            f"{request.idempotency_key or 'na'}"
        )
        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id=synthetic_id,
            message="Stub broker accepted order",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response=self._build_payload(request),
        )

    def cancel_order(self, request: BrokerCancelOrderRequest) -> BrokerActionResponse:
        health = self.health_check()
        if not health.ready:
            return BrokerActionResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="rejected",
                external_order_id=request.external_order_id,
                message="Broker credentials missing",
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
                order_id=request.order_id,
            )

        if self.is_live():
            return BrokerActionResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="not_implemented",
                external_order_id=request.external_order_id,
                message="FYERS live cancel integration pending",
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
                raw_response={"operation": "cancel", "pending": True},
                order_id=request.order_id,
            )

        return BrokerActionResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=True,
            status="cancelled",
            external_order_id=request.external_order_id,
            message="Stub broker cancelled order",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response={
                "operation": "cancel",
                "order_id": request.order_id,
                "external_order_id": request.external_order_id,
            },
            order_id=request.order_id,
        )

    def modify_order(self, request: BrokerModifyOrderRequest) -> BrokerActionResponse:
        health = self.health_check()
        if not health.ready:
            return BrokerActionResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="rejected",
                external_order_id=request.external_order_id,
                message="Broker credentials missing",
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
                order_id=request.order_id,
            )

        if self.is_live():
            return BrokerActionResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="not_implemented",
                external_order_id=request.external_order_id,
                message="FYERS live modify integration pending",
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
                raw_response={"operation": "modify", "pending": True},
                order_id=request.order_id,
            )

        return BrokerActionResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=True,
            status="modified",
            external_order_id=request.external_order_id,
            message="Stub broker modified order",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response={
                "operation": "modify",
                "order_id": request.order_id,
                "external_order_id": request.external_order_id,
                "quantity": request.quantity,
                "limit_price": request.limit_price,
                "stop_price": request.stop_price,
                "order_type": request.order_type,
                "validity": request.validity,
            },
            order_id=request.order_id,
        )
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
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._broker_adapter = broker_adapter
        self._lifecycle_store = lifecycle_store or InMemoryOrderLifecycleStore()
        self._state_machine = state_machine or OrderStateMachine()
        self._persistence_repository = persistence_repository
        self._update_consumer = update_consumer or BrokerUpdateConsumer()
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
from services.execution_service.app.order_state_machine import InvalidOrderTransition, OrderStateMachine
from services.execution_service.app.persistence import OrderPersistenceRepository
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


@app.post("/execution-service/broker/place-test")
def place_test() -> dict[str, object]:
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
from services.execution_service.app.service import (
    ExecutionService,
    OrderActionNotAllowedError,
    UnknownBrokerUpdateOrderError,
)
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

    def upsert_order(self, **kwargs) -> None:
        self.orders[kwargs["order_id"]] = {
            "order_id": kwargs["order_id"],
            "current_status": kwargs["current_status"].value,
            "external_order_id": kwargs["external_order_id"],
            "idempotency_key": kwargs["idempotency_key"],
        }

    def insert_event(self, event) -> None:
        self.events.append(event)

    def list_orders(self):
        return []

    def get_history(self, order_id: str):
        return []

    def active_order_count(self) -> int:
        return len([o for o in self.orders.values() if o["current_status"] not in {"filled", "cancelled", "rejected"}])

    def get_order_by_idempotency_key(self, idempotency_key: str):
        for order in self.orders.values():
            if order["idempotency_key"] == idempotency_key:
                class P:
                    pass
                p = P()
                p.order_id = order["order_id"]
                return p
        return None

    def get_order(self, order_id: str):
        if order_id not in self.orders:
            return None
        class P:
            pass
        p = P()
        p.order_id = order_id
        return p

    def get_order_by_external_order_id(self, external_order_id: str):
        for order in self.orders.values():
            if order["external_order_id"] == external_order_id:
                class P:
                    pass
                p = P()
                p.order_id = order["order_id"]
                return p
        return None


def build_service() -> ExecutionService:
    return ExecutionService(
        settings=build_settings("fyers_stub"),
        signal_reader=None,
        processor=ExecutionProcessor(settings=build_settings("fyers_stub")),
        broker_adapter=build_broker_adapter(build_settings("fyers_stub")),
        lifecycle_store=InMemoryOrderLifecycleStore(),
        state_machine=OrderStateMachine(),
        persistence_repository=FakePersistenceRepository(),
        update_consumer=BrokerUpdateConsumer(),
    )


def create_acknowledged_order(service: ExecutionService) -> str:
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id="manual-test-correlation",
        idempotency_key=f"idem-{datetime.now(UTC).timestamp()}",
    )
    result = service.submit_order_request(request, "manual submit")
    assert result.order_id is not None
    return result.order_id


def test_duplicate_manual_submission_returns_duplicate_response() -> None:
    service = build_service()
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id="manual-test-correlation",
        idempotency_key="manual-test-idempotency",
    )

    first = service.submit_order_request(request, "first submit")
    second = service.submit_order_request(request, "duplicate submit")

    assert first.status == "accepted"
    assert first.order_id is not None
    assert second.status == "duplicate"
    assert second.duplicate_of_order_id == first.order_id
    assert len(service.list_order_lifecycle()) == 1


def test_cancel_order_happy_path() -> None:
    service = build_service()
    order_id = create_acknowledged_order(service)

    result = service.cancel_order(order_id)
    history = service.get_order_history(order_id)

    assert result.accepted is True
    assert result.status == "cancelled"
    assert history[-2].to_status == OrderStatus.CANCEL_PENDING
    assert history[-1].to_status == OrderStatus.CANCELLED


def test_modify_order_happy_path() -> None:
    service = build_service()
    order_id = create_acknowledged_order(service)

    result = service.modify_order(order_id, quantity=2, limit_price=601.5)
    history = service.get_order_history(order_id)

    assert result.accepted is True
    assert result.status == "modified"
    assert history[-1].event_type == "broker_modify_ack"
    assert history[-1].to_status == OrderStatus.ACKNOWLEDGED


def test_cancel_not_allowed_from_filled() -> None:
    service = build_service()
    order_id = create_acknowledged_order(service)
    service.apply_broker_update(order_id=order_id, broker_status="OPEN", raw_payload={"status": "OPEN"})
    service.apply_broker_update(order_id=order_id, broker_status="COMPLETE", raw_payload={"status": "COMPLETE"})

    try:
        service.cancel_order(order_id)
    except OrderActionNotAllowedError as exc:
        assert "Cancel not allowed" in str(exc)
    else:
        raise AssertionError("Expected OrderActionNotAllowedError")


def test_modify_not_allowed_from_cancelled() -> None:
    service = build_service()
    order_id = create_acknowledged_order(service)
    service.cancel_order(order_id)

    try:
        service.modify_order(order_id, quantity=2)
    except OrderActionNotAllowedError as exc:
        assert "Modify not allowed" in str(exc)
    else:
        raise AssertionError("Expected OrderActionNotAllowedError")


def test_broker_update_consumer_normalizes_payload() -> None:
    consumer = BrokerUpdateConsumer()
    envelope = consumer.normalize_update(
        {"external_order_id": "ext-1", "status": "OPEN"},
        source="broker_webhook",
    )
    assert envelope.external_order_id == "ext-1"
    assert envelope.broker_status == "OPEN"
    assert envelope.source == "broker_webhook"


def test_consume_broker_update_by_external_order_id() -> None:
    service = build_service()
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id="manual-test-correlation",
        idempotency_key="manual-test-idempotency",
    )
    placed = service.submit_order_request(request, "manual submit")
    assert placed.order_id is not None
    assert placed.external_order_id is not None

    event = service.consume_broker_update(
        {"external_order_id": placed.external_order_id, "status": "OPEN"},
        source="broker_webhook",
    )
    assert event.order_id == placed.order_id
    assert event.to_status == OrderStatus.OPEN
    assert event.raw_payload is not None
    assert event.raw_payload["update_source"] == "broker_webhook"


def test_consume_broker_update_unknown_order_raises() -> None:
    service = build_service()
    try:
        service.consume_broker_update(
            {"external_order_id": "ext-missing", "status": "OPEN"},
            source="broker_webhook",
        )
    except UnknownBrokerUpdateOrderError as exc:
        assert "Unable to resolve order" in str(exc)
    else:
        raise AssertionError("Expected UnknownBrokerUpdateOrderError")
PY

cat > "$ROOT/tests/unit/test_execution_service_api.py" <<'PY'
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
from services.execution_service.app.models import (
    BrokerActionResponse,
    BrokerHealth,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
    OrderEventView,
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

    def prepare_once(self) -> list[dict[str, str]]:
        return [{"symbol": "NSE:SBIN-EQ", "timeframe": "1m", "bar_start_time": datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(), "side": "BUY", "quantity": "1", "broker": "fyers_stub", "status": "prepared"}]

    def place_first_prepared_order_once(self) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id="stub-order",
            message="Stub broker accepted order",
            correlation_id="corr",
            idempotency_key="idem",
            raw_response={"symbol": "NSE:SBIN-EQ"},
            order_id="ord-prepared-api",
        )

    def submit_order_request(self, request, submit_message: str) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id="stub-order",
            message=submit_message,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response={"symbol": "NSE:SBIN-EQ"},
            order_id="ord-manual-test-api",
        )

    def list_order_lifecycle(self):
        return []

    def get_order_history(self, order_id: str):
        return []

    def consume_broker_update(self, payload: dict[str, object], source: str = "api") -> OrderEventView:
        return OrderEventView(
            order_id="ord-manual-test-api",
            from_status=OrderStatus.ACKNOWLEDGED,
            to_status=OrderStatus.OPEN,
            event_type="broker_update",
            event_time=datetime(2026, 3, 18, 12, 1, tzinfo=UTC),
            message="Broker update mapped from OPEN",
            raw_payload={"external_order_id": "ext-1", "update_source": source},
        )

    def cancel_order(self, order_id: str) -> BrokerActionResponse:
        return BrokerActionResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="cancelled",
            external_order_id="stub-order",
            message="Stub broker cancelled order",
            correlation_id="corr",
            idempotency_key="idem",
            raw_response={"operation": "cancel"},
            order_id=order_id,
        )

    def modify_order(self, order_id: str, **kwargs) -> BrokerActionResponse:
        return BrokerActionResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="modified",
            external_order_id="stub-order",
            message="Stub broker modified order",
            correlation_id="corr",
            idempotency_key="idem",
            raw_response={"operation": "modify", **kwargs},
            order_id=order_id,
        )


execution_api.build_execution_service = lambda: FakeExecutionService()
execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_place_test_endpoint() -> None:
    response = client.post("/execution-service/broker/place-test")
    assert response.status_code == 200
    assert response.json()["order_id"] == "ord-manual-test-api"


def test_consume_broker_update_endpoint() -> None:
    response = client.post(
        "/execution-service/broker/consume-update",
        json={"external_order_id": "ext-1", "status": "OPEN"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["to_status"] == "open"


def test_cancel_endpoint() -> None:
    response = client.post("/execution-service/orders/ord-1/cancel")
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == "ord-1"
    assert body["status"] == "cancelled"


def test_modify_endpoint() -> None:
    response = client.post(
        "/execution-service/orders/ord-1/modify",
        json={"quantity": 2, "limit_price": 601.5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == "ord-1"
    assert body["status"] == "modified"
    assert body["raw_response"]["quantity"] == 2
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
marker = "# Item 29 — Cancel and modify order flows"
if marker not in text:
    addition = """

# Item 29 — Cancel and modify order flows
## Checklist

  * Add broker cancel request model
  * Add broker modify request model
  * Add broker action response model
  * Add cancel support in broker adapter
  * Add modify support in broker adapter
  * Add service cancel flow
  * Add service modify flow
  * Add lifecycle transitions for cancel pending and cancelled
  * Add lifecycle event for modify acknowledgement
  * Add API cancel endpoint
  * Add API modify endpoint
  * Add tests for cancel flow
  * Add tests for modify flow
  * Add validation for illegal cancel/modify states
  * Verify tests pass
  * Verify stub cancel and modify paths
  * Docs updated

## Definition of done

  * Code written
  * Cancel flow added
  * Modify flow added
  * State checks added
  * Broker stubs added
  * Tests added
  * Stub path verified
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 29 patch applied"

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

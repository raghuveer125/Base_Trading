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

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
    ExecutionRiskView,
    PortfolioPnlView,
    PortfolioView,
    PositionLotView,
    PositionPnlView,
    PositionView,
    TradeView,
)
from services.execution_service.app.order_state_machine import InvalidOrderTransition, OrderStateMachine
from services.execution_service.app.persistence import OrderPersistenceRepository
from services.execution_service.app.pnl import PnlService
from services.execution_service.app.portfolio import PortfolioService
from services.execution_service.app.position_persistence import PositionPersistenceRepository
from services.execution_service.app.positions import PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.execution_service.app.service import (
    ExecutionRiskRejectedError,
    ExecutionService,
    UnknownBrokerUpdateOrderError,
)
from services.execution_service.app.trade_persistence import TradePersistenceRepository
from services.execution_service.app.trades import InMemoryTradeLedger
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
_TRADE_LEDGER = InMemoryTradeLedger()
_PNL_SERVICE = PnlService()


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


def _build_trade_persistence_repository(settings) -> TradePersistenceRepository | None:
    if not settings.postgres_enabled:
        return None
    try:
        postgres_client = PostgresClient(settings=settings)
        postgres_client.connect()
        repository = TradePersistenceRepository(postgres_client=postgres_client)
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
    trade_persistence_repository = _build_trade_persistence_repository(settings)
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
        trade_ledger=_TRADE_LEDGER,
        trade_persistence_repository=trade_persistence_repository,
        pnl_service=_PNL_SERVICE,
    )


def build_lifecycle_only_service() -> ExecutionService:
    settings = get_settings()
    persistence_repository = _build_persistence_repository(settings)
    position_persistence_repository = _build_position_persistence_repository(settings)
    audit_persistence_repository = _build_audit_persistence_repository(settings)
    trade_persistence_repository = _build_trade_persistence_repository(settings)
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
        trade_ledger=_TRADE_LEDGER,
        trade_persistence_repository=trade_persistence_repository,
        pnl_service=_PNL_SERVICE,
    )



@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()

    broker_payload = {
        "adapter": "unknown",
        "mode": "unknown",
        "ready": False,
        "has_client_id": False,
        "has_access_token": False,
        "message": "Broker health not checked",
        "error_type": None,
        "error": None,
    }

    replay_ready = True
    approved_loaded = 0
    active_order_count = _LIFECYCLE_STORE.active_order_count()
    open_position_count = len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0])
    message = "Execution service ready"

    try:
        broker_adapter = build_broker_adapter(settings=settings)
        broker_health = broker_adapter.health_check()
        broker_payload.update(
            {
                "adapter": broker_health.adapter,
                "mode": broker_health.mode,
                "ready": broker_health.ready,
                "has_client_id": broker_health.has_client_id,
                "has_access_token": broker_health.has_access_token,
                "message": broker_health.message,
            }
        )
    except Exception as exc:
        broker_payload.update(
            {
                "message": f"Broker health check failed: {exc}",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        service = build_execution_service()
        status = service.get_status()
        replay_ready = status.replay_ready
        approved_loaded = status.approved_loaded
        active_order_count = status.active_order_count
        open_position_count = status.open_position_count
        message = status.message
    except Exception as exc:
        replay_ready = False
        message = f"Execution service degraded: {exc.__class__.__name__}: {exc}"

    return {
        "service": "execution_service",
        "mode": settings.execution_service_mode,
        "broker": settings.execution_service_broker,
        "broker_adapter": broker_payload["adapter"],
        "broker_mode": broker_payload["mode"],
        "broker_ready": broker_payload["ready"],
        "broker_has_client_id": broker_payload["has_client_id"],
        "broker_has_access_token": broker_payload["has_access_token"],
        "broker_error_type": broker_payload["error_type"],
        "broker_error": broker_payload["error"],
        "replay_ready": replay_ready,
        "approved_loaded": approved_loaded,
        "orders_prepared": 0,
        "active_order_count": active_order_count,
        "open_position_count": open_position_count,
        "last_prepared_at": None,
        "message": message,
        "status": "ok" if broker_payload["ready"] else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, object]:
    settings = get_settings()

    broker_payload = {
        "adapter": "unknown",
        "mode": "unknown",
        "ready": False,
        "has_client_id": False,
        "has_access_token": False,
        "message": "Broker health not checked",
        "error_type": None,
        "error": None,
    }

    try:
        broker_adapter = build_broker_adapter(settings=settings)
        broker_health = broker_adapter.health_check()
        broker_payload.update(
            {
                "adapter": broker_health.adapter,
                "mode": broker_health.mode,
                "ready": broker_health.ready,
                "has_client_id": broker_health.has_client_id,
                "has_access_token": broker_health.has_access_token,
                "message": broker_health.message,
            }
        )
    except Exception as exc:
        broker_payload.update(
            {
                "message": f"Broker health check failed: {exc}",
                "error_type": exc.__class__.__name__,
                "error": str(exc),
            }
        )

    try:
        status = build_execution_service().get_status()
        return {
            "service": status.service,
            "mode": status.mode,
            "broker": status.broker,
            "broker_adapter": status.broker_adapter,
            "broker_mode": status.broker_mode,
            "broker_ready": status.broker_ready,
            "broker_has_client_id": broker_payload["has_client_id"],
            "broker_has_access_token": broker_payload["has_access_token"],
            "broker_error_type": broker_payload["error_type"],
            "broker_error": broker_payload["error"],
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
            "broker_adapter": broker_payload["adapter"],
            "broker_mode": broker_payload["mode"],
            "broker_ready": broker_payload["ready"],
            "broker_has_client_id": broker_payload["has_client_id"],
            "broker_has_access_token": broker_payload["has_access_token"],
            "broker_error_type": broker_payload["error_type"] or exc.__class__.__name__,
            "broker_error": broker_payload["error"] or str(exc),
            "replay_ready": False,
            "approved_loaded": 0,
            "orders_prepared": 0,
            "active_order_count": _LIFECYCLE_STORE.active_order_count(),
            "open_position_count": len([p for p in _POSITION_SERVICE.list_positions() if p.net_quantity != 0]),
            "last_prepared_at": None,
            "message": f"Execution service degraded: {exc.__class__.__name__}: {exc}",
        }


@app.get("/execution-service/broker/health")
def broker_health() -> dict[str, object]:
    settings = get_settings()
    try:
        health = build_lifecycle_only_service().get_broker_health()
        return {
            "broker": health.broker,
            "adapter": health.adapter,
            "mode": health.mode,
            "ready": health.ready,
            "has_client_id": health.has_client_id,
            "has_access_token": health.has_access_token,
            "checked_at": health.checked_at.isoformat(),
            "message": health.message,
            "error_type": None,
            "error": None,
        }
    except Exception as exc:
        return {
            "broker": settings.execution_service_broker,
            "adapter": "unknown",
            "mode": "unknown",
            "ready": False,
            "has_client_id": bool(getattr(settings, "fyers_client_id", "")),
            "has_access_token": bool(getattr(settings, "fyers_access_token", "")),
            "checked_at": None,
            "message": f"Broker health check failed: {exc}",
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }



@app.post("/execution-service/marks")
def set_mark_price(payload: dict[str, object]) -> dict[str, object]:
    service = build_lifecycle_only_service()
    symbol = str(payload.get("symbol"))
    price = float(payload.get("price"))
    service.set_mark_price(symbol, price)
    return {
        "service": "execution_service",
        "symbol": symbol,
        "mark_price": price,
        "status": "ok",
    }


@app.get("/execution-service/pnl/positions/{symbol}")
def get_position_pnl(symbol: str) -> dict[str, object]:
    service = build_lifecycle_only_service()
    snap = service.get_position_pnl(symbol)
    return {
        "service": "execution_service",
        "position_pnl": PositionPnlView(
            symbol=snap.symbol,
            side=snap.side,
            net_quantity=snap.net_quantity,
            avg_price=snap.avg_price,
            mark_price=snap.mark_price,
            unrealized_pnl=snap.unrealized_pnl,
            realized_pnl=snap.realized_pnl,
            total_pnl=snap.total_pnl,
            updated_at=snap.updated_at,
        ).model_dump(mode="json"),
    }


@app.get("/execution-service/pnl/portfolio")
def get_portfolio_pnl() -> dict[str, object]:
    service = build_lifecycle_only_service()
    snap = service.get_portfolio_pnl()
    return {
        "service": "execution_service",
        "portfolio_pnl": PortfolioPnlView(
            realized_pnl=snap.realized_pnl,
            unrealized_pnl=snap.unrealized_pnl,
            total_pnl=snap.total_pnl,
            updated_at=snap.updated_at,
            positions=[
                PositionPnlView(
                    symbol=p.symbol,
                    side=p.side,
                    net_quantity=p.net_quantity,
                    avg_price=p.avg_price,
                    mark_price=p.mark_price,
                    unrealized_pnl=p.unrealized_pnl,
                    realized_pnl=p.realized_pnl,
                    total_pnl=p.total_pnl,
                    updated_at=p.updated_at,
                )
                for p in snap.positions
            ],
        ).model_dump(mode="json"),
    }


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


@app.post("/execution-service/broker/place")
def place_manual_order(payload: dict[str, object]) -> dict[str, object]:
    request = BrokerPlaceOrderRequest(
        symbol=str(payload.get("symbol", "NSE:SBIN-EQ")),
        side=str(payload.get("side", "BUY")),
        quantity=int(payload.get("quantity", 1)),
        order_type=str(payload.get("order_type", "MARKET")),
        product=str(payload.get("product", "INTRADAY")),
        validity=str(payload.get("validity", "DAY")),
        limit_price=float(payload.get("limit_price", 0.0)),
        stop_price=float(payload.get("stop_price", 0.0)),
        disclosed_qty=int(payload.get("disclosed_qty", 0)),
        offline_order=bool(payload.get("offline_order", False)),
        stop_loss=float(payload.get("stop_loss", 0.0)),
        take_profit=float(payload.get("take_profit", 0.0)),
        correlation_id=str(payload.get("correlation_id", f"manual-order-correlation-{datetime.utcnow().timestamp()}")),
        idempotency_key=str(payload.get("idempotency_key", f"manual-order-idempotency-{datetime.utcnow().timestamp()}")),
    )
    service = build_lifecycle_only_service()
    try:
        result = service.submit_order_request(request=request, submit_message="Manual order submitted to broker adapter")
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
        result = service.submit_order_request(request=request, submit_message="Manual test order submitted to broker adapter")
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

    return {"service": "execution_service", "event": event.model_dump(mode="json")}


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


@app.get("/execution-service/trades")
def list_trades(symbol: str | None = None) -> dict[str, object]:
    service = build_lifecycle_only_service()
    trades = service.list_trades(symbol=symbol)
    return {
        "service": "execution_service",
        "count": len(trades),
        "trades": [
            TradeView(
                trade_id=t.trade_id,
                symbol=t.symbol,
                entry_side=t.entry_side,
                entry_quantity=t.entry_quantity,
                entry_price=t.entry_price,
                entry_time=t.entry_time,
                exit_quantity=t.exit_quantity,
                exit_price=t.exit_price,
                exit_time=t.exit_time,
                realized_pnl=t.realized_pnl,
                status=t.status,
                entry_order_id=t.entry_order_id,
                exit_order_id=t.exit_order_id,
                metadata=t.metadata,
            ).model_dump(mode="json")
            for t in trades
        ],
    }


@app.get("/execution-service/trades/{symbol}")
def list_trades_by_symbol(symbol: str) -> dict[str, object]:
    service = build_lifecycle_only_service()
    trades = service.list_trades(symbol=symbol)
    return {
        "service": "execution_service",
        "symbol": symbol,
        "count": len(trades),
        "trades": [
            TradeView(
                trade_id=t.trade_id,
                symbol=t.symbol,
                entry_side=t.entry_side,
                entry_quantity=t.entry_quantity,
                entry_price=t.entry_price,
                entry_time=t.entry_time,
                exit_quantity=t.exit_quantity,
                exit_price=t.exit_price,
                exit_time=t.exit_time,
                realized_pnl=t.realized_pnl,
                status=t.status,
                entry_order_id=t.entry_order_id,
                exit_order_id=t.exit_order_id,
                metadata=t.metadata,
            ).model_dump(mode="json")
            for t in trades
        ],
    }

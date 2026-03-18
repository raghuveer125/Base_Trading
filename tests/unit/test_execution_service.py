from datetime import UTC, datetime

from services.execution_service.app.audit import InMemoryAuditTrail
from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.execution_risk import ExecutionRiskGuard
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.models import BrokerPlaceOrderRequest
from services.execution_service.app.pnl import PnlService
from services.execution_service.app.order_state_machine import OrderStateMachine
from services.execution_service.app.portfolio import PortfolioService
from services.execution_service.app.positions import PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.trades import InMemoryTradeLedger
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
            max_symbol_position_quantity=10,
            max_open_positions=5,
        ),
        audit_trail=InMemoryAuditTrail(),
        trade_ledger=InMemoryTradeLedger(),
        pnl_service=PnlService(),
    )


def create_and_fill(service: ExecutionService, symbol: str, side: str, qty: int, price: float) -> str:
    request = BrokerPlaceOrderRequest(
        symbol=symbol,
        side=side,
        quantity=qty,
        correlation_id=f"corr-{symbol}-{side}-{datetime.now(UTC).timestamp()}",
        idempotency_key=f"idem-{symbol}-{side}-{datetime.now(UTC).timestamp()}",
    )
    result = service.submit_order_request(request, "submit")
    assert result.order_id is not None
    service.consume_broker_update({"order_id": result.order_id, "status": "OPEN"}, source="test")
    service.consume_broker_update(
        {"order_id": result.order_id, "status": "COMPLETE", "filledQty": qty, "avgPrice": price},
        source="test",
    )
    return result.order_id


def test_position_pnl_snapshot_long() -> None:
    service = build_service()
    create_and_fill(service, "NSE:SBIN-EQ", "BUY", 1, 600.0)
    service.set_mark_price("NSE:SBIN-EQ", 615.0)
    snap = service.get_position_pnl("NSE:SBIN-EQ")
    assert snap.unrealized_pnl == 15.0
    assert snap.realized_pnl == 0.0
    assert snap.total_pnl == 15.0


def test_position_pnl_snapshot_after_round_trip() -> None:
    service = build_service()
    create_and_fill(service, "NSE:SBIN-EQ", "BUY", 1, 600.0)
    create_and_fill(service, "NSE:SBIN-EQ", "SELL", 1, 610.0)
    service.set_mark_price("NSE:SBIN-EQ", 620.0)
    snap = service.get_position_pnl("NSE:SBIN-EQ")
    assert snap.unrealized_pnl == 0.0
    assert snap.realized_pnl == 10.0
    assert snap.total_pnl == 10.0


def test_portfolio_pnl_snapshot_multiple_positions() -> None:
    service = build_service()
    create_and_fill(service, "NSE:SBIN-EQ", "BUY", 1, 600.0)
    create_and_fill(service, "NSE:RELIANCE-EQ", "BUY", 1, 2500.0)
    service.set_mark_price("NSE:SBIN-EQ", 610.0)
    service.set_mark_price("NSE:RELIANCE-EQ", 2520.0)
    snap = service.get_portfolio_pnl()
    assert snap.unrealized_pnl == 30.0
    assert snap.realized_pnl == 0.0
    assert snap.total_pnl == 30.0
    assert len(snap.positions) == 2

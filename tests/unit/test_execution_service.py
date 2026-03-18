from datetime import UTC, datetime

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.lifecycle_store import InMemoryOrderLifecycleStore
from services.execution_service.app.portfolio import PortfolioService
from services.execution_service.app.models import BrokerPlaceOrderRequest
from services.execution_service.app.order_state_machine import OrderStateMachine
from services.execution_service.app.position_persistence import PositionPersistenceRepository
from services.execution_service.app.positions import FillEvent, PositionService
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
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


class FakePositionPersistenceRepository:
    def __init__(self) -> None:
        self.positions = {}

    def upsert_position(self, snapshot) -> None:
        self.positions[snapshot.symbol] = snapshot

    def get_position(self, symbol: str):
        snapshot = self.positions.get(symbol)
        if snapshot is None:
            return None
        from services.execution_service.app.models import PositionLotView, PositionView
        return PositionView(
            symbol=snapshot.symbol,
            net_quantity=snapshot.net_quantity,
            avg_price=snapshot.avg_price,
            side=snapshot.side,
            realized_pnl=snapshot.realized_pnl,
            open_lots=[PositionLotView(quantity=l.quantity, price=l.price, side=l.side) for l in snapshot.open_lots],
            updated_at=snapshot.updated_at,
        )

    def list_positions(self):
        return [self.get_position(symbol) for symbol in sorted(self.positions.keys())]


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
        position_persistence_repository=FakePositionPersistenceRepository(),
    )


def create_and_fill_order(service: ExecutionService, symbol: str, side: str, qty: int, price: float) -> str:
    request = BrokerPlaceOrderRequest(
        symbol=symbol,
        side=side,
        quantity=qty,
        correlation_id=f"corr-{symbol}-{datetime.now(UTC).timestamp()}",
        idempotency_key=f"idem-{symbol}-{datetime.now(UTC).timestamp()}",
    )
    result = service.submit_order_request(request, "submit")
    assert result.order_id is not None
    service.consume_broker_update({"order_id": result.order_id, "status": "OPEN"}, source="test")
    service.consume_broker_update(
        {"order_id": result.order_id, "status": "COMPLETE", "filledQty": qty, "avgPrice": price},
        source="test",
    )
    return result.order_id


def test_position_snapshot_is_persisted_after_fill() -> None:
    service = build_service()
    create_and_fill_order(service, "NSE:SBIN-EQ", "BUY", 1, 600.25)
    position = service.get_position("NSE:SBIN-EQ")
    assert position.net_quantity == 1
    assert position.avg_price == 600.25
    assert position.side == "LONG"


def test_portfolio_reads_from_persisted_positions() -> None:
    service = build_service()
    create_and_fill_order(service, "NSE:SBIN-EQ", "BUY", 1, 600.0)
    create_and_fill_order(service, "NSE:RELIANCE-EQ", "BUY", 2, 2500.0)
    portfolio = service.get_portfolio()
    assert portfolio.open_position_count == 2
    assert portfolio.gross_quantity == 3
    assert portfolio.symbols == ["NSE:RELIANCE-EQ", "NSE:SBIN-EQ"]


def test_round_trip_realized_pnl_visible_in_persisted_position() -> None:
    service = build_service()
    create_and_fill_order(service, "NSE:SBIN-EQ", "BUY", 1, 600.0)
    create_and_fill_order(service, "NSE:SBIN-EQ", "SELL", 1, 610.0)
    position = service.get_position("NSE:SBIN-EQ")
    assert position.net_quantity == 0
    assert position.realized_pnl == 10.0

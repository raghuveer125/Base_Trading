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

    def get_order_by_idempotency_key(self, idempotency_key: str):
        for order in self.orders.values():
            if order["idempotency_key"] == idempotency_key:
                class P:
                    pass
                p = P()
                p.order_id = order["order_id"]
                return p
        return None


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
    assert result.order_id is not None
    assert len(orders) == 1
    assert orders[0].current_status == OrderStatus.ACKNOWLEDGED
    assert orders[0].history_count == 2
    assert len(repo.events) == 2
    assert len(repo.orders) == 1


def test_duplicate_manual_submission_returns_duplicate_response() -> None:
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
    assert len(store.list_orders()) == 1


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


def test_register_manual_test_order_is_idempotent() -> None:
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
    first_id = service.register_manual_test_order(response)
    second_id = service.register_manual_test_order(response)

    assert first_id == second_id
    assert len(repo.orders) == 1
    assert len(repo.events) == 2

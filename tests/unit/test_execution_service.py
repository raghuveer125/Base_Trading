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
            "symbol": kwargs["symbol"],
            "side": kwargs["side"],
            "quantity": kwargs["quantity"],
            "broker": kwargs["broker"],
            "current_status": kwargs["current_status"].value,
            "external_order_id": kwargs["external_order_id"],
            "correlation_id": kwargs["correlation_id"],
            "idempotency_key": kwargs["idempotency_key"],
            "latest_message": kwargs["latest_message"],
            "last_updated_at": kwargs["last_updated_at"],
        }

    def insert_event(self, event) -> None:
        self.events.append(event)

    def list_orders(self):
        from services.execution_service.app.models import OrderLifecycleView
        from services.execution_service.app.order_state_machine import OrderStatus

        result = []
        for order in self.orders.values():
            history_count = len([e for e in self.events if e.order_id == order["order_id"]])
            result.append(
                OrderLifecycleView(
                    order_id=order["order_id"],
                    symbol=order["symbol"],
                    side=order["side"],
                    quantity=order["quantity"],
                    broker=order["broker"],
                    current_status=OrderStatus(order["current_status"]),
                    history_count=history_count,
                    external_order_id=order["external_order_id"],
                    correlation_id=order["correlation_id"],
                    idempotency_key=order["idempotency_key"],
                    latest_message=order["latest_message"],
                    last_updated_at=order["last_updated_at"],
                )
            )
        return result

    def get_history(self, order_id: str):
        from services.execution_service.app.models import OrderEventView
        from services.execution_service.app.order_state_machine import OrderStatus

        result = []
        for event in self.events:
            if event.order_id == order_id:
                result.append(
                    OrderEventView(
                        order_id=event.order_id,
                        from_status=OrderStatus(event.from_status),
                        to_status=OrderStatus(event.to_status),
                        event_type=event.event_type,
                        event_time=event.event_time,
                        message=event.message,
                        filled_quantity=event.filled_quantity,
                        remaining_quantity=event.remaining_quantity,
                        average_price=event.average_price,
                        raw_payload=event.raw_payload,
                    )
                )
        return result

    def active_order_count(self) -> int:
        return len(
            [o for o in self.orders.values() if o["current_status"] not in {"filled", "cancelled", "rejected"}]
        )

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

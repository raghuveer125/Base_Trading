from datetime import UTC, datetime
from decimal import Decimal

from services.bar_builder.app.cache_writer import BarBuilderCacheWriter
from services.bar_builder.app.processor import BarBuilderProcessor
from services.bar_builder.app.publisher import BarPublisher
from services.bar_builder.app.repository import ClosedBarRepository
from services.bar_builder.app.service import BarBuilderService
from services.bar_builder.app.state_store import InMemoryBarStateStore
from shared.config.settings import Settings
from shared.kafka.producer import KafkaEventProducer
from shared.postgres.client import PostgresClient
from shared.redis.client import RedisStateClient


def build_settings(kafka_enabled: bool = False, redis_enabled: bool = False, postgres_enabled: bool = False) -> Settings:
    return Settings(
        APP_ENV="local",
        APP_NAME="projectX",
        LOG_LEVEL="INFO",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="projectx",
        POSTGRES_USER="projectx",
        POSTGRES_PASSWORD="changeme",
        POSTGRES_ENABLED=postgres_enabled,
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_ENABLED=redis_enabled,
        REDIS_KEY_PREFIX="projectx",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_TOPIC_TICKS="md.raw.tick",
        KAFKA_TOPIC_BARS_1M="md.bar.1m",
        KAFKA_TOPIC_BARS_1M_CLOSED="md.bar.1m.closed",
        KAFKA_CLIENT_ID="projectx-mdg",
        KAFKA_ENABLED=kafka_enabled,
        KAFKA_AUTO_CREATE_TOPICS=True,
        KAFKA_TOPIC_PARTITIONS=1,
        KAFKA_TOPIC_REPLICATION_FACTOR=1,
        KAFKA_CONSUMER_GROUP_BAR_BUILDER="projectx-bar-builder",
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
    )


class FakeKafkaConsumer:
    def connect(self) -> None:
        return None

    def poll(self, timeout_ms: int = 1000, max_records: int = 10) -> list[dict]:
        return [
            {
                "topic": "md.raw.tick",
                "partition": 0,
                "offset": 1,
                "key": "NSE:SBIN-EQ",
                "value": {
                    "meta": {
                        "event_id": "1",
                        "event_type": "tick",
                        "event_version": "1.0",
                        "source": "market_data_gateway",
                        "created_at": "2026-03-17T17:00:00+00:00",
                        "correlation_id": None,
                    },
                    "payload": {
                        "symbol": "NSE:SBIN-EQ",
                        "exchange": "NSE",
                        "last_traded_price": "820.15",
                        "last_traded_quantity": 5,
                        "last_trade_time": "2026-03-17T17:00:05+00:00",
                        "received_at": "2026-03-17T17:00:05+00:00",
                    },
                },
            },
            {
                "topic": "md.raw.tick",
                "partition": 0,
                "offset": 2,
                "key": "NSE:SBIN-EQ",
                "value": {
                    "meta": {
                        "event_id": "2",
                        "event_type": "tick",
                        "event_version": "1.0",
                        "source": "market_data_gateway",
                        "created_at": "2026-03-17T17:00:00+00:00",
                        "correlation_id": None,
                    },
                    "payload": {
                        "symbol": "NSE:SBIN-EQ",
                        "exchange": "NSE",
                        "last_traded_price": "821.25",
                        "last_traded_quantity": 7,
                        "last_trade_time": "2026-03-17T17:00:35+00:00",
                        "received_at": "2026-03-17T17:00:35+00:00",
                    },
                },
            },
            {
                "topic": "md.raw.tick",
                "partition": 0,
                "offset": 3,
                "key": "NSE:SBIN-EQ",
                "value": {
                    "meta": {
                        "event_id": "3",
                        "event_type": "tick",
                        "event_version": "1.0",
                        "source": "market_data_gateway",
                        "created_at": "2026-03-17T17:00:00+00:00",
                        "correlation_id": None,
                    },
                    "payload": {
                        "symbol": "NSE:SBIN-EQ",
                        "exchange": "NSE",
                        "last_traded_price": "819.90",
                        "last_traded_quantity": 6,
                        "last_trade_time": "2026-03-17T17:01:05+00:00",
                        "received_at": "2026-03-17T17:01:05+00:00",
                    },
                },
            },
        ]


def test_processor_creates_and_updates_bar() -> None:
    processor = BarBuilderProcessor()

    first_tick = {
        "payload": {
            "symbol": "NSE:SBIN-EQ",
            "exchange": "NSE",
            "last_traded_price": "820.15",
            "last_traded_quantity": 5,
            "last_trade_time": "2026-03-17T17:00:05+00:00",
            "received_at": "2026-03-17T17:00:05+00:00",
        }
    }
    second_tick = {
        "payload": {
            "symbol": "NSE:SBIN-EQ",
            "exchange": "NSE",
            "last_traded_price": "821.25",
            "last_traded_quantity": 7,
            "last_trade_time": "2026-03-17T17:00:35+00:00",
            "received_at": "2026-03-17T17:00:35+00:00",
        }
    }

    created_bar = processor.create_bar_from_tick(first_tick, timeframe="1m")
    updated_bar = processor.update_existing_bar(created_bar, second_tick)

    assert created_bar.payload.open == created_bar.payload.high == created_bar.payload.low == created_bar.payload.close
    assert updated_bar.payload.open == created_bar.payload.open
    assert updated_bar.payload.high == Decimal("821.25")
    assert updated_bar.payload.low == Decimal("820.15")
    assert updated_bar.payload.close == Decimal("821.25")
    assert updated_bar.payload.volume == 12
    assert updated_bar.payload.bar_start_time == datetime(2026, 3, 17, 17, 0, tzinfo=UTC)
    assert updated_bar.payload.bar_end_time == datetime(2026, 3, 17, 17, 1, tzinfo=UTC)


def test_bar_builder_service_consumes_aggregates_closes_and_persists() -> None:
    settings = build_settings(kafka_enabled=False, redis_enabled=False, postgres_enabled=False)
    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()

    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    state_store = InMemoryBarStateStore()
    publisher = BarPublisher(
        settings=settings,
        kafka_producer=kafka_producer,
    )
    cache_writer = BarBuilderCacheWriter(
        settings=settings,
        redis_client=redis_client,
    )
    repository = ClosedBarRepository(
        postgres_client=postgres_client,
    )

    service = BarBuilderService(
        settings=settings,
        consumer=FakeKafkaConsumer(),
        processor=BarBuilderProcessor(),
        publisher=publisher,
        state_store=state_store,
        cache_writer=cache_writer,
        repository=repository,
    )
    service.connect()

    built_count = service.consume_and_build_once()
    status = service.get_status()

    assert built_count == 3
    assert status.connected is True
    assert status.consumed_count == 3
    assert status.produced_count == 3
    assert status.closed_count == 1
    assert status.open_bar_count == 1
    assert status.source_topic == "md.raw.tick"
    assert status.target_topic == "md.bar.1m"
    assert status.closed_topic == "md.bar.1m.closed"
    assert publisher.closed_count() == 1
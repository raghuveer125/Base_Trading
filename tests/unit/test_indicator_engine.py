from datetime import UTC, datetime

from services.indicator_engine.app.cache_writer import IndicatorCacheWriter
from services.indicator_engine.app.processor import IndicatorProcessor
from services.indicator_engine.app.publisher import IndicatorPublisher
from services.indicator_engine.app.repository import IndicatorRepository
from services.indicator_engine.app.service import IndicatorEngineService
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
        KAFKA_TOPIC_INDICATORS_1M="md.indicator.1m",
        KAFKA_CLIENT_ID="projectx-mdg",
        KAFKA_ENABLED=kafka_enabled,
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
    )


class FakeClosedBarConsumer:
    def connect(self) -> None:
        return None

    def poll(self, timeout_ms: int = 1000, max_records: int = 10) -> list[dict]:
        return [
            {
                "topic": "md.bar.1m.closed",
                "partition": 0,
                "offset": 1,
                "key": "NSE:SBIN-EQ|1m|closed",
                "value": {
                    "meta": {
                        "event_id": "1",
                        "event_type": "bar",
                        "event_version": "1.0",
                        "source": "bar_builder",
                        "created_at": "2026-03-17T17:01:00+00:00",
                        "correlation_id": None,
                    },
                    "payload": {
                        "symbol": "NSE:SBIN-EQ",
                        "exchange": "NSE",
                        "timeframe": "1m",
                        "bar_start_time": "2026-03-17T17:00:00+00:00",
                        "bar_end_time": "2026-03-17T17:01:00+00:00",
                        "open": "820.10",
                        "high": "821.00",
                        "low": "819.90",
                        "close": "820.50",
                        "volume": 100,
                        "source_detail": "test",
                        "revision": 1,
                    },
                },
            }
        ]


def test_processor_builds_indicator_from_bar() -> None:
    processor = IndicatorProcessor()

    bar_event = {
        "payload": {
            "symbol": "NSE:SBIN-EQ",
            "exchange": "NSE",
            "timeframe": "1m",
            "bar_start_time": datetime(2026, 3, 17, 17, 0, tzinfo=UTC),
            "bar_end_time": datetime(2026, 3, 17, 17, 1, tzinfo=UTC),
            "open": "820.10",
            "high": "821.00",
            "low": "819.90",
            "close": "820.50",
            "volume": 100,
            "source_detail": "test",
            "revision": 1,
        }
    }

    event = processor.build_indicator_from_bar(bar_event=bar_event, timeframe="1m")

    assert event.payload.symbol == "NSE:SBIN-EQ"
    assert event.payload.timeframe == "1m"
    assert str(event.payload.values.ema_7) == "820.50"
    assert str(event.payload.values.sma_5) == "820.50"


def test_indicator_engine_service_consumes_publishes_caches_and_persists() -> None:
    settings = build_settings(kafka_enabled=False, redis_enabled=False, postgres_enabled=False)
    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()

    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    service = IndicatorEngineService(
        settings=settings,
        consumer=FakeClosedBarConsumer(),
        processor=IndicatorProcessor(),
        publisher=IndicatorPublisher(
            settings=settings,
            kafka_producer=kafka_producer,
        ),
        cache_writer=IndicatorCacheWriter(
            settings=settings,
            redis_client=redis_client,
        ),
        repository=IndicatorRepository(
            postgres_client=postgres_client,
        ),
    )
    service.connect()

    produced_count = service.consume_and_calculate_once()
    status = service.get_status()

    assert produced_count == 1
    assert status.connected is True
    assert status.consumed_count == 1
    assert status.produced_count == 1
    assert status.source_topic == "md.bar.1m.closed"
    assert status.target_topic == "md.indicator.1m"
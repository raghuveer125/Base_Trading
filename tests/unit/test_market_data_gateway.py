from datetime import UTC, datetime
from decimal import Decimal

from services.market_data_gateway.app.cache_writer import MarketDataCacheWriter
from services.market_data_gateway.app.feed_stub import StubPriceFeed
from services.market_data_gateway.app.models import RawMarketPacket
from services.market_data_gateway.app.normalizer import MarketDataNormalizer
from services.market_data_gateway.app.publisher import MarketDataPublisher
from services.market_data_gateway.app.service import MarketDataGatewayService
from shared.config.settings import Settings
from shared.kafka.producer import KafkaEventProducer
from shared.redis.client import RedisStateClient


def build_settings() -> Settings:
    return Settings(
        APP_ENV="local",
        APP_NAME="projectX",
        LOG_LEVEL="INFO",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="projectx",
        POSTGRES_USER="projectx",
        POSTGRES_PASSWORD="changeme",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_ENABLED=False,
        REDIS_KEY_PREFIX="projectx",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_TOPIC_TICKS="md.raw.tick",
        KAFKA_TOPIC_BARS_1M="md.bar.1m",
        KAFKA_TOPIC_BARS_1M_CLOSED="md.bar.1m.closed",
        KAFKA_CLIENT_ID="projectx-mdg",
        KAFKA_ENABLED=False,
        KAFKA_AUTO_CREATE_TOPICS=False,
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


def test_normalize_tick() -> None:
    packet = RawMarketPacket(
        symbol="nse:sbin-eq",
        exchange="NSE",
        ltp=Decimal("820.15"),
        ltq=10,
        last_trade_time=datetime(2026, 3, 17, 9, 15, tzinfo=UTC),
    )
    event = MarketDataNormalizer().normalize_tick(packet)

    assert event.payload.symbol == "NSE:SBIN-EQ"
    assert event.payload.exchange == "NSE"
    assert event.payload.last_traded_price == Decimal("820.15")
    assert event.payload.last_traded_quantity == 10


def test_publisher_counts_events() -> None:
    settings = build_settings()
    packet = RawMarketPacket(
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        ltp=Decimal("820.15"),
        ltq=10,
        last_trade_time=datetime(2026, 3, 17, 9, 15, tzinfo=UTC),
    )
    event = MarketDataNormalizer().normalize_tick(packet)
    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()
    publisher = MarketDataPublisher(
        settings=settings,
        kafka_producer=kafka_producer,
    )

    publisher.publish_tick(event)

    assert publisher.published_count() == 1


def test_gateway_emit_once() -> None:
    settings = build_settings()
    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()

    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    service = MarketDataGatewayService(
        settings=settings,
        normalizer=MarketDataNormalizer(),
        publisher=MarketDataPublisher(
            settings=settings,
            kafka_producer=kafka_producer,
        ),
        stub_feed=StubPriceFeed(),
        cache_writer=MarketDataCacheWriter(
            settings=settings,
            redis_client=redis_client,
        ),
    )
    service.connect()

    emitted = service.emit_once()
    status = service.get_status()

    assert emitted == 2
    assert status.connected is True
    assert status.service == "market_data_gateway"
    assert status.mode == "stub"
    assert status.subscribed_symbols == ["NSE:SBIN-EQ", "NSE:RELIANCE-EQ"]
    assert status.last_emit_at is not None
from datetime import UTC, datetime
from decimal import Decimal

from services.market_data_gateway.app.cache_writer import MarketDataCacheWriter
from services.market_data_gateway.app.models import GatewayStatus
from shared.config.settings import Settings
from shared.models import TickEvent
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


def build_tick_event() -> TickEvent:
    return TickEvent.create(
        source="market_data_gateway",
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        last_traded_price=Decimal("820.15"),
        last_trade_time=datetime(2026, 3, 17, 17, 0, tzinfo=UTC),
        received_at=datetime(2026, 3, 17, 17, 0, 1, tzinfo=UTC),
        last_traded_quantity=10,
    )


def test_cache_tick_and_status_do_not_fail_when_redis_disabled() -> None:
    settings = build_settings()
    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    writer = MarketDataCacheWriter(
        settings=settings,
        redis_client=redis_client,
    )

    writer.cache_tick(build_tick_event())
    writer.cache_status(
        GatewayStatus(
            service="market_data_gateway",
            mode="stub",
            connected=True,
            subscribed_symbols=["NSE:SBIN-EQ"],
            last_emit_at=None,
            message="Gateway connected",
        )
    )
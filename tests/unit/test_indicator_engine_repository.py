from datetime import UTC, datetime
from decimal import Decimal

from services.indicator_engine.app.repository import IndicatorRepository
from shared.config.settings import Settings
from shared.models import IndicatorEvent, IndicatorValues
from shared.postgres.client import PostgresClient


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
    )


def build_indicator_event() -> IndicatorEvent:
    return IndicatorEvent.create(
        source="indicator_engine",
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        timeframe="1m",
        bar_start_time=datetime(2026, 3, 17, 17, 0, tzinfo=UTC),
        values=IndicatorValues(
            ema_7=Decimal("820.50"),
            ema_9=Decimal("820.50"),
            sma_3=Decimal("820.50"),
            sma_5=Decimal("820.50"),
        ),
    )


def test_repository_methods_do_not_fail_when_postgres_disabled() -> None:
    settings = build_settings()
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()
    repository.upsert_indicator(build_indicator_event())
    assert repository.count_indicators() is None
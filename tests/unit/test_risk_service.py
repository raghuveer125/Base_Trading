from datetime import UTC, datetime
from decimal import Decimal

from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.service import RiskService
from shared.config.settings import Settings
from shared.models import IndicatorEvent, IndicatorValues


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
        STRATEGY_RUNTIME_MODE="stub",
        STRATEGY_RUNTIME_API_HOST="127.0.0.1",
        STRATEGY_RUNTIME_API_PORT=8005,
        STRATEGY_RUNTIME_NAME="ema_sma_cross_stub",
        RISK_SERVICE_MODE="stub",
        RISK_SERVICE_API_HOST="127.0.0.1",
        RISK_SERVICE_API_PORT=8006,
        RISK_MAX_OPEN_POSITIONS=5,
        RISK_MAX_SIGNAL_SIZE=1,
    )


class FakeSignalReader:
    def load_signals(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": "NSE:SBIN-EQ",
                "timeframe": "1m",
                "bar_start_time": datetime(2026, 3, 17, 17, 0, tzinfo=UTC).isoformat(),
                "signal": "BUY",
            },
            {
                "symbol": "NSE:RELIANCE-EQ",
                "timeframe": "1m",
                "bar_start_time": datetime(2026, 3, 17, 17, 1, tzinfo=UTC).isoformat(),
                "signal": "HOLD",
            },
        ]


def test_risk_processor_filters_hold_signal() -> None:
    processor = RiskProcessor(settings=build_settings())
    approved, rejected = processor.apply_risk(FakeSignalReader().load_signals())

    assert len(approved) == 1
    assert len(rejected) == 1
    assert approved[0]["signal"] == "BUY"
    assert rejected[0]["reason"] == "hold_signal"


def test_risk_service_evaluates_once() -> None:
    service = RiskService(
        settings=build_settings(),
        signal_reader=FakeSignalReader(),
        processor=RiskProcessor(settings=build_settings()),
    )

    result = service.evaluate_once()
    status = service.get_status()

    assert len(result["approved"]) == 1
    assert len(result["rejected"]) == 1
    assert status.service == "risk_service"
    assert status.signals_loaded == 2
    assert status.approved_signals == 1
    assert status.rejected_signals == 1
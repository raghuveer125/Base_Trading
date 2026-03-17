from shared.config.settings import Settings
from shared.kafka.admin import KafkaTopicAdmin


def build_settings(kafka_enabled: bool, kafka_auto_create_topics: bool) -> Settings:
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
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_TOPIC_TICKS="md.raw.tick",
        KAFKA_CLIENT_ID="projectx-mdg",
        KAFKA_ENABLED=kafka_enabled,
        KAFKA_AUTO_CREATE_TOPICS=kafka_auto_create_topics,
        KAFKA_TOPIC_PARTITIONS=1,
        KAFKA_TOPIC_REPLICATION_FACTOR=1,
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
    )


def test_kafka_admin_skips_when_disabled() -> None:
    admin = KafkaTopicAdmin(settings=build_settings(kafka_enabled=False, kafka_auto_create_topics=False))
    admin.connect()
    admin.ensure_topic("md.raw.tick")
    admin.close()


def test_kafka_admin_skips_when_auto_create_disabled() -> None:
    admin = KafkaTopicAdmin(settings=build_settings(kafka_enabled=False, kafka_auto_create_topics=True))
    admin.connect()
    admin.ensure_topic("md.raw.tick")
    admin.close()
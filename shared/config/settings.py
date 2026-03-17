from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="local", alias="APP_ENV")
    app_name: str = Field(default="projectX", alias="APP_NAME")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="projectx", alias="POSTGRES_DB")
    postgres_user: str = Field(default="projectx", alias="POSTGRES_USER")
    postgres_password: str = Field(default="changeme", alias="POSTGRES_PASSWORD")
    postgres_enabled: bool = Field(default=False, alias="POSTGRES_ENABLED")

    redis_host: str = Field(default="localhost", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")
    redis_enabled: bool = Field(default=False, alias="REDIS_ENABLED")
    redis_key_prefix: str = Field(default="projectx", alias="REDIS_KEY_PREFIX")

    kafka_bootstrap_servers: str = Field(default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS")
    kafka_topic_ticks: str = Field(default="md.raw.tick", alias="KAFKA_TOPIC_TICKS")
    kafka_topic_bars_1m: str = Field(default="md.bar.1m", alias="KAFKA_TOPIC_BARS_1M")
    kafka_topic_bars_1m_closed: str = Field(default="md.bar.1m.closed", alias="KAFKA_TOPIC_BARS_1M_CLOSED")
    kafka_topic_indicators_1m: str = Field(default="md.indicator.1m", alias="KAFKA_TOPIC_INDICATORS_1M")
    kafka_client_id: str = Field(default="projectx-mdg", alias="KAFKA_CLIENT_ID")
    kafka_enabled: bool = Field(default=False, alias="KAFKA_ENABLED")
    kafka_auto_create_topics: bool = Field(default=False, alias="KAFKA_AUTO_CREATE_TOPICS")
    kafka_topic_partitions: int = Field(default=1, alias="KAFKA_TOPIC_PARTITIONS")
    kafka_topic_replication_factor: int = Field(default=1, alias="KAFKA_TOPIC_REPLICATION_FACTOR")
    kafka_consumer_group_bar_builder: str = Field(
        default="projectx-bar-builder",
        alias="KAFKA_CONSUMER_GROUP_BAR_BUILDER",
    )
    kafka_consumer_group_indicator_engine: str = Field(
        default="projectx-indicator-engine",
        alias="KAFKA_CONSUMER_GROUP_INDICATOR_ENGINE",
    )
    kafka_consumer_auto_offset_reset: str = Field(
        default="earliest",
        alias="KAFKA_CONSUMER_AUTO_OFFSET_RESET",
    )

    fyers_client_id: str = Field(default="", alias="FYERS_CLIENT_ID")
    fyers_secret_key: str = Field(default="", alias="FYERS_SECRET_KEY")
    fyers_redirect_uri: str = Field(default="", alias="FYERS_REDIRECT_URI")
    fyers_access_token: str = Field(default="", alias="FYERS_ACCESS_TOKEN")

    auth_session_file: str = Field(default="data/auth/session.json", alias="AUTH_SESSION_FILE")
    auth_request_timeout_seconds: float = Field(default=10.0, alias="AUTH_REQUEST_TIMEOUT_SECONDS")
    auth_validate_on_startup: bool = Field(default=False, alias="AUTH_VALIDATE_ON_STARTUP")
    auth_service_mode: str = Field(default="bootstrap", alias="AUTH_SERVICE_MODE")

    mdg_mode: str = Field(default="stub", alias="MDG_MODE")
    mdg_symbols: str = Field(default="NSE:SBIN-EQ,NSE:RELIANCE-EQ", alias="MDG_SYMBOLS")
    mdg_exchange: str = Field(default="NSE", alias="MDG_EXCHANGE")
    mdg_emit_interval_seconds: float = Field(default=1.0, alias="MDG_EMIT_INTERVAL_SECONDS")
    mdg_api_host: str = Field(default="127.0.0.1", alias="MDG_API_HOST")
    mdg_api_port: int = Field(default=8002, alias="MDG_API_PORT")

    bar_builder_mode: str = Field(default="stub", alias="BAR_BUILDER_MODE")
    bar_builder_api_host: str = Field(default="127.0.0.1", alias="BAR_BUILDER_API_HOST")
    bar_builder_api_port: int = Field(default=8003, alias="BAR_BUILDER_API_PORT")
    bar_builder_timeframe: str = Field(default="1m", alias="BAR_BUILDER_TIMEFRAME")
    bar_builder_close_on_next_minute: bool = Field(default=True, alias="BAR_BUILDER_CLOSE_ON_NEXT_MINUTE")

    indicator_engine_mode: str = Field(default="stub", alias="INDICATOR_ENGINE_MODE")
    indicator_engine_api_host: str = Field(default="127.0.0.1", alias="INDICATOR_ENGINE_API_HOST")
    indicator_engine_api_port: int = Field(default=8004, alias="INDICATOR_ENGINE_API_PORT")
    indicator_engine_timeframe: str = Field(default="1m", alias="INDICATOR_ENGINE_TIMEFRAME")

    strategy_runtime_mode: str = Field(default="stub", alias="STRATEGY_RUNTIME_MODE")
    strategy_runtime_api_host: str = Field(default="127.0.0.1", alias="STRATEGY_RUNTIME_API_HOST")
    strategy_runtime_api_port: int = Field(default=8005, alias="STRATEGY_RUNTIME_API_PORT")
    strategy_runtime_name: str = Field(default="ema_sma_cross_stub", alias="STRATEGY_RUNTIME_NAME")

    risk_service_mode: str = Field(default="stub", alias="RISK_SERVICE_MODE")
    risk_service_api_host: str = Field(default="127.0.0.1", alias="RISK_SERVICE_API_HOST")
    risk_service_api_port: int = Field(default=8006, alias="RISK_SERVICE_API_PORT")
    risk_max_open_positions: int = Field(default=5, alias="RISK_MAX_OPEN_POSITIONS")
    risk_max_signal_size: int = Field(default=1, alias="RISK_MAX_SIGNAL_SIZE")

    execution_service_mode: str = Field(default="stub", alias="EXECUTION_SERVICE_MODE")
    execution_service_api_host: str = Field(default="127.0.0.1", alias="EXECUTION_SERVICE_API_HOST")
    execution_service_api_port: int = Field(default=8007, alias="EXECUTION_SERVICE_API_PORT")
    execution_service_broker: str = Field(default="fyers_stub", alias="EXECUTION_SERVICE_BROKER")

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def is_local(self) -> bool:
        return self.app_env.lower() == "local"

    @property
    def mdg_symbol_list(self) -> list[str]:
        return [symbol.strip() for symbol in self.mdg_symbols.split(",") if symbol.strip()]

    @property
    def postgres_dsn(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value
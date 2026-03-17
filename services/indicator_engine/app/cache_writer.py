from __future__ import annotations

from services.indicator_engine.app.models import IndicatorEngineStatus
from shared.config.settings import Settings
from shared.logging.logger import get_logger
from shared.models import IndicatorEvent
from shared.redis.client import RedisStateClient


class IndicatorCacheWriter:
    def __init__(self, settings: Settings, redis_client: RedisStateClient) -> None:
        self._settings = settings
        self._redis_client = redis_client
        self._logger = get_logger("indicator_engine.cache_writer")

    def cache_indicator(self, event: IndicatorEvent) -> None:
        key = self._redis_client.build_key(
            "indicator_engine",
            "indicator",
            event.payload.symbol,
            event.payload.timeframe,
        )
        self._redis_client.set_json(key, event.model_dump(mode="json"))
        self._logger.info(
            "indicator_cached",
            key=key,
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
        )

    def cache_status(self, status: IndicatorEngineStatus) -> None:
        key = self._redis_client.build_key("indicator_engine", "status")
        payload = {
            "service": status.service,
            "mode": status.mode,
            "connected": status.connected,
            "source_topic": status.source_topic,
            "target_topic": status.target_topic,
            "timeframe": status.timeframe,
            "consumed_count": status.consumed_count,
            "produced_count": status.produced_count,
            "last_processed_at": status.last_processed_at.isoformat() if status.last_processed_at else None,
            "message": status.message,
        }
        self._redis_client.set_json(key, payload)
        self._logger.info(
            "indicator_engine_status_cached",
            key=key,
        )
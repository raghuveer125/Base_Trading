from __future__ import annotations

from services.bar_builder.app.state_store import InMemoryBarStateStore
from shared.config.settings import Settings
from shared.logging.logger import get_logger
from shared.models import BarEvent
from shared.redis.client import RedisStateClient


class BarBuilderCacheWriter:
    def __init__(self, settings: Settings, redis_client: RedisStateClient) -> None:
        self._settings = settings
        self._redis_client = redis_client
        self._logger = get_logger("bar_builder.cache_writer")

    def cache_open_bar(self, event: BarEvent) -> None:
        key = self._redis_client.build_key(
            "bar_builder",
            "open_bar",
            event.payload.symbol,
            event.payload.timeframe,
        )
        self._redis_client.set_json(key, event.model_dump(mode="json"))
        self._logger.info(
            "open_bar_cached",
            key=key,
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
        )

    def cache_closed_bar(self, event: BarEvent) -> None:
        key = self._redis_client.build_key(
            "bar_builder",
            "closed_bar",
            event.payload.symbol,
            event.payload.timeframe,
        )
        self._redis_client.set_json(key, event.model_dump(mode="json"))
        self._logger.info(
            "closed_bar_cached",
            key=key,
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
        )

    def cache_status(self, state_store: InMemoryBarStateStore, consumed_count: int, produced_count: int, closed_count: int) -> None:
        key = self._redis_client.build_key("bar_builder", "status")
        payload = {
            "service": "bar_builder",
            "open_bar_count": state_store.size(),
            "consumed_count": consumed_count,
            "produced_count": produced_count,
            "closed_count": closed_count,
        }
        self._redis_client.set_json(key, payload)
        self._logger.info(
            "bar_builder_status_cached",
            key=key,
        )
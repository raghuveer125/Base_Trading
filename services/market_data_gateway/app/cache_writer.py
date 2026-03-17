from __future__ import annotations

from services.market_data_gateway.app.models import GatewayStatus
from shared.config.settings import Settings
from shared.logging.logger import get_logger
from shared.models import TickEvent
from shared.redis.client import RedisStateClient


class MarketDataCacheWriter:
    def __init__(self, settings: Settings, redis_client: RedisStateClient) -> None:
        self._settings = settings
        self._redis_client = redis_client
        self._logger = get_logger("market_data_gateway.cache_writer")

    def cache_tick(self, event: TickEvent) -> None:
        key = self._redis_client.build_key(
            "market_data_gateway",
            "tick",
            event.payload.symbol,
        )
        self._redis_client.set_json(key, event.model_dump(mode="json"))
        self._logger.info(
            "tick_cached",
            key=key,
            symbol=event.payload.symbol,
        )

    def cache_status(self, status: GatewayStatus) -> None:
        key = self._redis_client.build_key("market_data_gateway", "status")
        payload = {
            "service": status.service,
            "mode": status.mode,
            "connected": status.connected,
            "subscribed_symbols": status.subscribed_symbols,
            "last_emit_at": status.last_emit_at.isoformat() if status.last_emit_at else None,
            "message": status.message,
        }
        self._redis_client.set_json(key, payload)
        self._logger.info(
            "market_data_gateway_status_cached",
            key=key,
        )
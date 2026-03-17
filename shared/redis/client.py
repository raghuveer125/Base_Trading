from __future__ import annotations

import json
from typing import Any

import redis

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class RedisStateClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("shared.redis.client")
        self._client: redis.Redis | None = None

    def connect(self) -> None:
        if not self._settings.redis_enabled:
            self._logger.info(
                "redis_disabled",
                host=self._settings.redis_host,
                port=self._settings.redis_port,
            )
            return

        self._client = redis.Redis(
            host=self._settings.redis_host,
            port=self._settings.redis_port,
            decode_responses=True,
        )
        self._client.ping()

        self._logger.info(
            "redis_connected",
            host=self._settings.redis_host,
            port=self._settings.redis_port,
        )

    def build_key(self, *parts: str) -> str:
        suffix = ":".join(parts)
        return f"{self._settings.redis_key_prefix}:{suffix}"

    def set_json(self, key: str, value: dict[str, Any]) -> None:
        if not self._settings.redis_enabled:
            self._logger.info(
                "redis_set_skipped",
                reason="redis_disabled",
                key=key,
            )
            return

        if self._client is None:
            raise RuntimeError("Redis client is not connected")

        self._client.set(key, json.dumps(value))

        self._logger.info(
            "redis_key_set",
            key=key,
        )

    def get_json(self, key: str) -> dict[str, Any] | None:
        if not self._settings.redis_enabled:
            self._logger.info(
                "redis_get_skipped",
                reason="redis_disabled",
                key=key,
            )
            return None

        if self._client is None:
            raise RuntimeError("Redis client is not connected")

        raw = self._client.get(key)
        if raw is None:
            return None

        return json.loads(raw)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
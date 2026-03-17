from __future__ import annotations

import json
from typing import Any

from kafka import KafkaProducer

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class KafkaEventProducer:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("shared.kafka.producer")
        self._producer: KafkaProducer | None = None

    def connect(self) -> None:
        if not self._settings.kafka_enabled:
            self._logger.info(
                "kafka_disabled",
                bootstrap_servers=self._settings.kafka_bootstrap_servers,
            )
            return

        self._producer = KafkaProducer(
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=self._settings.kafka_client_id,
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8"),
            acks="all",
            retries=3,
        )

        self._logger.info(
            "kafka_connected",
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=self._settings.kafka_client_id,
        )

    def publish(self, topic: str, key: str, value: dict[str, Any]) -> None:
        if not self._settings.kafka_enabled:
            self._logger.info(
                "kafka_publish_skipped",
                reason="kafka_disabled",
                topic=topic,
                key=key,
            )
            return

        if self._producer is None:
            raise RuntimeError("Kafka producer is not connected")

        future = self._producer.send(topic, key=key, value=value)
        metadata = future.get(timeout=10)

        self._logger.info(
            "kafka_message_published",
            topic=metadata.topic,
            partition=metadata.partition,
            offset=metadata.offset,
            key=key,
        )

    def flush(self) -> None:
        if self._producer is not None:
            self._producer.flush()

    def close(self) -> None:
        if self._producer is not None:
            self._producer.close()
            self._producer = None
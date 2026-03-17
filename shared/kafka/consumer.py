from __future__ import annotations

import json
from typing import Any

from kafka import KafkaConsumer

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class KafkaEventConsumer:
    def __init__(self, settings: Settings, topic: str, group_id: str) -> None:
        self._settings = settings
        self._topic = topic
        self._group_id = group_id
        self._logger = get_logger("shared.kafka.consumer")
        self._consumer: KafkaConsumer | None = None

    def connect(self) -> None:
        if not self._settings.kafka_enabled:
            self._logger.info(
                "kafka_consumer_skipped",
                reason="kafka_disabled",
                topic=self._topic,
                group_id=self._group_id,
            )
            return

        self._consumer = KafkaConsumer(
            self._topic,
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            client_id=f"{self._settings.kafka_client_id}-consumer",
            group_id=self._group_id,
            auto_offset_reset=self._settings.kafka_consumer_auto_offset_reset,
            enable_auto_commit=True,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            key_deserializer=lambda key: key.decode("utf-8") if key is not None else None,
        )

        self._logger.info(
            "kafka_consumer_connected",
            bootstrap_servers=self._settings.kafka_bootstrap_servers,
            topic=self._topic,
            group_id=self._group_id,
        )

    def poll(self, timeout_ms: int = 1000, max_records: int = 10) -> list[dict[str, Any]]:
        if not self._settings.kafka_enabled:
            self._logger.info(
                "kafka_consume_skipped",
                reason="kafka_disabled",
                topic=self._topic,
                group_id=self._group_id,
            )
            return []

        if self._consumer is None:
            raise RuntimeError("Kafka consumer is not connected")

        records_map = self._consumer.poll(timeout_ms=timeout_ms, max_records=max_records)
        records: list[dict[str, Any]] = []

        for _, messages in records_map.items():
            for message in messages:
                records.append(
                    {
                        "topic": message.topic,
                        "partition": message.partition,
                        "offset": message.offset,
                        "key": message.key,
                        "value": message.value,
                    }
                )

        self._logger.info(
            "kafka_records_polled",
            topic=self._topic,
            group_id=self._group_id,
            record_count=len(records),
        )

        return records

    def close(self) -> None:
        if self._consumer is not None:
            self._consumer.close()
            self._consumer = None
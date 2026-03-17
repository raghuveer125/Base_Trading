from __future__ import annotations

from shared.config.settings import Settings
from shared.kafka.producer import KafkaEventProducer
from shared.logging.logger import get_logger
from shared.models import BarEvent


class BarPublisher:
    def __init__(self, settings: Settings, kafka_producer: KafkaEventProducer) -> None:
        self._settings = settings
        self._kafka_producer = kafka_producer
        self._logger = get_logger("bar_builder.publisher")
        self._published_events: list[BarEvent] = []
        self._closed_events: list[BarEvent] = []

    def publish_bar(self, event: BarEvent) -> None:
        self._published_events.append(event)

        payload = event.model_dump(mode="json")
        key = f"{event.payload.symbol}|{event.payload.timeframe}"

        self._kafka_producer.publish(
            topic=self._settings.kafka_topic_bars_1m,
            key=key,
            value=payload,
        )

        self._logger.info(
            "bar_published",
            service="bar_builder",
            topic=self._settings.kafka_topic_bars_1m,
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
            close=str(event.payload.close),
        )

    def publish_closed_bar(self, event: BarEvent) -> None:
        self._closed_events.append(event)

        payload = event.model_dump(mode="json")
        key = f"{event.payload.symbol}|{event.payload.timeframe}|closed"

        self._kafka_producer.publish(
            topic=self._settings.kafka_topic_bars_1m_closed,
            key=key,
            value=payload,
        )

        self._logger.info(
            "closed_bar_published",
            service="bar_builder",
            topic=self._settings.kafka_topic_bars_1m_closed,
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
            close=str(event.payload.close),
        )

    def published_count(self) -> int:
        return len(self._published_events)

    def closed_count(self) -> int:
        return len(self._closed_events)
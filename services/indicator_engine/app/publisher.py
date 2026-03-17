from __future__ import annotations

from shared.config.settings import Settings
from shared.kafka.producer import KafkaEventProducer
from shared.logging.logger import get_logger
from shared.models import IndicatorEvent


class IndicatorPublisher:
    def __init__(self, settings: Settings, kafka_producer: KafkaEventProducer) -> None:
        self._settings = settings
        self._kafka_producer = kafka_producer
        self._logger = get_logger("indicator_engine.publisher")
        self._published_events: list[IndicatorEvent] = []

    def publish_indicator(self, event: IndicatorEvent) -> None:
        self._published_events.append(event)

        payload = event.model_dump(mode="json")
        key = f"{event.payload.symbol}|{event.payload.timeframe}"

        self._kafka_producer.publish(
            topic=self._settings.kafka_topic_indicators_1m,
            key=key,
            value=payload,
        )

        self._logger.info(
            "indicator_published",
            service="indicator_engine",
            topic=self._settings.kafka_topic_indicators_1m,
            symbol=event.payload.symbol,
            timeframe=event.payload.timeframe,
        )

    def published_count(self) -> int:
        return len(self._published_events)
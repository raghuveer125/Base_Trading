from __future__ import annotations

from shared.config.settings import Settings
from shared.kafka.producer import KafkaEventProducer
from shared.logging.logger import get_logger
from shared.models import TickEvent


class MarketDataPublisher:
    def __init__(self, settings: Settings, kafka_producer: KafkaEventProducer) -> None:
        self._settings = settings
        self._kafka_producer = kafka_producer
        self._logger = get_logger("market_data_gateway.publisher")
        self._published_events: list[TickEvent] = []

    def publish_tick(self, event: TickEvent) -> None:
        self._published_events.append(event)

        payload = event.model_dump(mode="json")
        key = event.payload.symbol

        self._kafka_producer.publish(
            topic=self._settings.kafka_topic_ticks,
            key=key,
            value=payload,
        )

        self._logger.info(
            "tick_published",
            service="market_data_gateway",
            topic=self._settings.kafka_topic_ticks,
            symbol=event.payload.symbol,
            exchange=event.payload.exchange,
            last_traded_price=str(event.payload.last_traded_price),
            last_trade_time=event.payload.last_trade_time.isoformat(),
        )

    def published_count(self) -> int:
        return len(self._published_events)
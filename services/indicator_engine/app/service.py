from __future__ import annotations

from datetime import UTC, datetime

from services.indicator_engine.app.cache_writer import IndicatorCacheWriter
from services.indicator_engine.app.models import IndicatorEngineStatus
from services.indicator_engine.app.processor import IndicatorProcessor
from services.indicator_engine.app.publisher import IndicatorPublisher
from services.indicator_engine.app.repository import IndicatorRepository
from shared.config.settings import Settings
from shared.kafka.consumer import KafkaEventConsumer


class IndicatorEngineService:
    def __init__(
        self,
        settings: Settings,
        consumer: KafkaEventConsumer,
        processor: IndicatorProcessor,
        publisher: IndicatorPublisher,
        cache_writer: IndicatorCacheWriter,
        repository: IndicatorRepository,
    ) -> None:
        self._settings = settings
        self._consumer = consumer
        self._processor = processor
        self._publisher = publisher
        self._cache_writer = cache_writer
        self._repository = repository
        self._connected = False
        self._consumed_count = 0
        self._produced_count = 0
        self._last_processed_at: datetime | None = None

    def connect(self) -> None:
        self._consumer.connect()
        self._repository.ensure_table()
        self._connected = True

    def consume_and_calculate_once(self) -> int:
        if not self._connected:
            raise RuntimeError("Indicator engine is not connected")

        records = self._consumer.poll(timeout_ms=1000, max_records=10)
        produced = 0

        for record in records:
            bar_event = record["value"]
            indicator_event = self._processor.build_indicator_from_bar(
                bar_event=bar_event,
                timeframe=self._settings.indicator_engine_timeframe,
            )
            self._publisher.publish_indicator(indicator_event)
            self._cache_writer.cache_indicator(indicator_event)
            self._repository.upsert_indicator(indicator_event)
            self._consumed_count += 1
            self._produced_count += 1
            self._last_processed_at = datetime.now(UTC)
            produced += 1

        self._cache_writer.cache_status(self.get_status())
        return produced

    def get_status(self) -> IndicatorEngineStatus:
        return IndicatorEngineStatus(
            service="indicator_engine",
            mode=self._settings.indicator_engine_mode,
            connected=self._connected,
            source_topic=self._settings.kafka_topic_bars_1m_closed,
            target_topic=self._settings.kafka_topic_indicators_1m,
            timeframe=self._settings.indicator_engine_timeframe,
            consumed_count=self._consumed_count,
            produced_count=self._produced_count,
            last_processed_at=self._last_processed_at,
            message="Indicator engine connected" if self._connected else "Indicator engine not connected",
        )
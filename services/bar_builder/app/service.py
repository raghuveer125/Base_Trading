from __future__ import annotations

from datetime import UTC, datetime

from services.bar_builder.app.cache_writer import BarBuilderCacheWriter
from services.bar_builder.app.models import BarBuilderStatus
from services.bar_builder.app.processor import BarBuilderProcessor
from services.bar_builder.app.publisher import BarPublisher
from services.bar_builder.app.repository import ClosedBarRepository
from services.bar_builder.app.state_store import InMemoryBarStateStore
from shared.config.settings import Settings
from shared.kafka.consumer import KafkaEventConsumer
from shared.logging.logger import get_logger


class BarBuilderService:
    def __init__(
        self,
        settings: Settings,
        consumer: KafkaEventConsumer,
        processor: BarBuilderProcessor,
        publisher: BarPublisher,
        state_store: InMemoryBarStateStore,
        cache_writer: BarBuilderCacheWriter,
        repository: ClosedBarRepository,
    ) -> None:
        self._settings = settings
        self._consumer = consumer
        self._processor = processor
        self._publisher = publisher
        self._state_store = state_store
        self._cache_writer = cache_writer
        self._repository = repository
        self._logger = get_logger("bar_builder.service")
        self._connected = False
        self._consumed_count = 0
        self._produced_count = 0
        self._closed_count = 0
        self._last_processed_at: datetime | None = None

    def connect(self) -> None:
        self._consumer.connect()
        self._repository.ensure_table()
        self._connected = True

    def _close_completed_bars(self, current_bar_start_time: datetime) -> int:
        if not self._settings.bar_builder_close_on_next_minute:
            return 0

        keys_to_close: list[str] = []

        for key, bar_event in self._state_store.items():
            if bar_event.payload.bar_start_time < current_bar_start_time:
                keys_to_close.append(key)

        closed = 0
        for key in keys_to_close:
            bar_event = self._state_store.pop(key)
            if bar_event is None:
                continue
            self._publisher.publish_closed_bar(bar_event)
            self._cache_writer.cache_closed_bar(bar_event)
            self._repository.upsert_closed_bar(bar_event)
            self._closed_count += 1
            closed += 1
            self._logger.info(
                "bar_closed",
                service="bar_builder",
                symbol=bar_event.payload.symbol,
                timeframe=bar_event.payload.timeframe,
                bar_start_time=bar_event.payload.bar_start_time.isoformat(),
            )

        return closed

    def consume_and_build_once(self) -> int:
        if not self._connected:
            raise RuntimeError("Bar builder is not connected")

        records = self._consumer.poll(timeout_ms=1000, max_records=10)
        built = 0

        for record in records:
            tick_event = record["value"]
            payload = tick_event["payload"]
            bar_start_time, _ = self._processor.get_bar_window(tick_event)

            self._close_completed_bars(bar_start_time)

            key = self._processor.build_bar_key(
                symbol=payload["symbol"],
                timeframe=self._settings.bar_builder_timeframe,
                bar_start_time=bar_start_time,
            )

            existing_bar = self._state_store.get(key)
            if existing_bar is None:
                bar_event = self._processor.create_bar_from_tick(
                    tick_event=tick_event,
                    timeframe=self._settings.bar_builder_timeframe,
                )
            else:
                bar_event = self._processor.update_existing_bar(
                    existing_bar=existing_bar,
                    tick_event=tick_event,
                )

            self._state_store.set(key, bar_event)
            self._publisher.publish_bar(bar_event)
            self._cache_writer.cache_open_bar(bar_event)

            self._consumed_count += 1
            self._produced_count += 1
            self._last_processed_at = datetime.now(UTC)
            built += 1

        self._cache_writer.cache_status(
            state_store=self._state_store,
            consumed_count=self._consumed_count,
            produced_count=self._produced_count,
            closed_count=self._closed_count,
        )

        return built

    def get_status(self) -> BarBuilderStatus:
        return BarBuilderStatus(
            service="bar_builder",
            mode=self._settings.bar_builder_mode,
            connected=self._connected,
            source_topic=self._settings.kafka_topic_ticks,
            target_topic=self._settings.kafka_topic_bars_1m,
            closed_topic=self._settings.kafka_topic_bars_1m_closed,
            timeframe=self._settings.bar_builder_timeframe,
            consumed_count=self._consumed_count,
            produced_count=self._produced_count,
            closed_count=self._closed_count,
            open_bar_count=self._state_store.size(),
            last_processed_at=self._last_processed_at,
            message="Bar builder connected" if self._connected else "Bar builder not connected",
        )
import asyncio
import os

import uvicorn

from services.bar_builder.app.api import app
from services.bar_builder.app.cache_writer import BarBuilderCacheWriter
from services.bar_builder.app.processor import BarBuilderProcessor
from services.bar_builder.app.publisher import BarPublisher
from services.bar_builder.app.repository import ClosedBarRepository
from services.bar_builder.app.service import BarBuilderService
from services.bar_builder.app.state_store import InMemoryBarStateStore
from shared.config.settings import get_settings
from shared.kafka.consumer import KafkaEventConsumer
from shared.kafka.producer import KafkaEventProducer
from shared.logging.logger import configure_logging, get_logger
from shared.postgres.client import PostgresClient
from shared.redis.client import RedisStateClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("bar_builder")

    consumer = KafkaEventConsumer(
        settings=settings,
        topic=settings.kafka_topic_ticks,
        group_id=settings.kafka_consumer_group_bar_builder,
    )
    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()

    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    service = BarBuilderService(
        settings=settings,
        consumer=consumer,
        processor=BarBuilderProcessor(),
        publisher=BarPublisher(
            settings=settings,
            kafka_producer=kafka_producer,
        ),
        state_store=InMemoryBarStateStore(),
        cache_writer=BarBuilderCacheWriter(
            settings=settings,
            redis_client=redis_client,
        ),
        repository=ClosedBarRepository(
            postgres_client=postgres_client,
        ),
    )
    service.connect()

    logger.info(
        "service_started",
        service="bar_builder",
        env=settings.app_env,
        mode=settings.bar_builder_mode,
        source_topic=settings.kafka_topic_ticks,
        target_topic=settings.kafka_topic_bars_1m,
        closed_topic=settings.kafka_topic_bars_1m_closed,
        redis_enabled=settings.redis_enabled,
        postgres_enabled=settings.postgres_enabled,
    )

    built_count = service.consume_and_build_once()
    kafka_producer.flush()
    kafka_producer.close()
    redis_client.close()
    postgres_client.close()

    logger.info(
        "bar_build_complete",
        service="bar_builder",
        built_count=built_count,
        closed_count=service.get_status().closed_count,
        open_bar_count=service.get_status().open_bar_count,
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("bar_builder")

    logger.info(
        "bar_builder_api_starting",
        service="bar_builder",
        env=settings.app_env,
        host=settings.bar_builder_api_host,
        port=settings.bar_builder_api_port,
        redis_enabled=settings.redis_enabled,
        postgres_enabled=settings.postgres_enabled,
    )

    uvicorn.run(
        app,
        host=settings.bar_builder_api_host,
        port=settings.bar_builder_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("BAR_BUILDER_MODE", "stub").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
import asyncio
import os

import uvicorn

from services.indicator_engine.app.api import app
from services.indicator_engine.app.cache_writer import IndicatorCacheWriter
from services.indicator_engine.app.processor import IndicatorProcessor
from services.indicator_engine.app.publisher import IndicatorPublisher
from services.indicator_engine.app.repository import IndicatorRepository
from services.indicator_engine.app.service import IndicatorEngineService
from shared.config.settings import get_settings
from shared.kafka.consumer import KafkaEventConsumer
from shared.kafka.producer import KafkaEventProducer
from shared.logging.logger import configure_logging, get_logger
from shared.postgres.client import PostgresClient
from shared.redis.client import RedisStateClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("indicator_engine")

    consumer = KafkaEventConsumer(
        settings=settings,
        topic=settings.kafka_topic_bars_1m_closed,
        group_id=settings.kafka_consumer_group_indicator_engine,
    )
    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()

    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    service = IndicatorEngineService(
        settings=settings,
        consumer=consumer,
        processor=IndicatorProcessor(),
        publisher=IndicatorPublisher(
            settings=settings,
            kafka_producer=kafka_producer,
        ),
        cache_writer=IndicatorCacheWriter(
            settings=settings,
            redis_client=redis_client,
        ),
        repository=IndicatorRepository(
            postgres_client=postgres_client,
        ),
    )
    service.connect()

    logger.info(
        "service_started",
        service="indicator_engine",
        env=settings.app_env,
        mode=settings.indicator_engine_mode,
        source_topic=settings.kafka_topic_bars_1m_closed,
        target_topic=settings.kafka_topic_indicators_1m,
        redis_enabled=settings.redis_enabled,
        postgres_enabled=settings.postgres_enabled,
    )

    produced_count = service.consume_and_calculate_once()
    kafka_producer.flush()
    kafka_producer.close()
    redis_client.close()
    postgres_client.close()

    logger.info(
        "indicator_calculation_complete",
        service="indicator_engine",
        produced_count=produced_count,
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("indicator_engine")

    logger.info(
        "indicator_engine_api_starting",
        service="indicator_engine",
        env=settings.app_env,
        host=settings.indicator_engine_api_host,
        port=settings.indicator_engine_api_port,
        redis_enabled=settings.redis_enabled,
        postgres_enabled=settings.postgres_enabled,
    )

    uvicorn.run(
        app,
        host=settings.indicator_engine_api_host,
        port=settings.indicator_engine_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("INDICATOR_ENGINE_MODE", "stub").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
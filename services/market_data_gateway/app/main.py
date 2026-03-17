import asyncio
import os

import uvicorn

from services.market_data_gateway.app.api import app
from services.market_data_gateway.app.cache_writer import MarketDataCacheWriter
from services.market_data_gateway.app.feed_stub import StubPriceFeed
from services.market_data_gateway.app.normalizer import MarketDataNormalizer
from services.market_data_gateway.app.publisher import MarketDataPublisher
from services.market_data_gateway.app.service import MarketDataGatewayService
from shared.config.settings import get_settings
from shared.kafka.admin import KafkaTopicAdmin
from shared.kafka.producer import KafkaEventProducer
from shared.logging.logger import configure_logging, get_logger
from shared.redis.client import RedisStateClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("market_data_gateway")

    topic_admin = KafkaTopicAdmin(settings=settings)
    topic_admin.connect()
    topic_admin.ensure_topic(settings.kafka_topic_ticks)

    kafka_producer = KafkaEventProducer(settings=settings)
    kafka_producer.connect()

    redis_client = RedisStateClient(settings=settings)
    redis_client.connect()

    service = MarketDataGatewayService(
        settings=settings,
        normalizer=MarketDataNormalizer(),
        publisher=MarketDataPublisher(
            settings=settings,
            kafka_producer=kafka_producer,
        ),
        stub_feed=StubPriceFeed(),
        cache_writer=MarketDataCacheWriter(
            settings=settings,
            redis_client=redis_client,
        ),
    )
    service.connect()

    logger.info(
        "service_started",
        service="market_data_gateway",
        env=settings.app_env,
        mode=settings.mdg_mode,
        subscribed_symbols=settings.mdg_symbol_list,
        kafka_enabled=settings.kafka_enabled,
        kafka_topic_ticks=settings.kafka_topic_ticks,
        redis_enabled=settings.redis_enabled,
    )

    emitted = service.emit_once()
    kafka_producer.flush()
    kafka_producer.close()
    topic_admin.close()
    redis_client.close()

    logger.info(
        "stub_emit_complete",
        service="market_data_gateway",
        emitted_count=emitted,
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("market_data_gateway")

    logger.info(
        "mdg_api_starting",
        service="market_data_gateway",
        env=settings.app_env,
        host=settings.mdg_api_host,
        port=settings.mdg_api_port,
        kafka_enabled=settings.kafka_enabled,
        redis_enabled=settings.redis_enabled,
    )

    uvicorn.run(
        app,
        host=settings.mdg_api_host,
        port=settings.mdg_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("MDG_MODE", "stub").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
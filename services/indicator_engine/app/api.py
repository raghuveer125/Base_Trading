from fastapi import FastAPI

from services.indicator_engine.app.cache_writer import IndicatorCacheWriter
from services.indicator_engine.app.processor import IndicatorProcessor
from services.indicator_engine.app.publisher import IndicatorPublisher
from services.indicator_engine.app.replay_api import router as replay_router
from services.indicator_engine.app.repository import IndicatorRepository
from services.indicator_engine.app.service import IndicatorEngineService
from shared.config.settings import get_settings
from shared.kafka.consumer import KafkaEventConsumer
from shared.kafka.producer import KafkaEventProducer
from shared.postgres.client import PostgresClient
from shared.redis.client import RedisStateClient

app = FastAPI(title="indicator_engine", version="0.1.0")
app.include_router(replay_router)


def build_indicator_engine_service() -> IndicatorEngineService:
    settings = get_settings()

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
    return service


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    status = build_indicator_engine_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "connected": status.connected,
        "source_topic": status.source_topic,
        "target_topic": status.target_topic,
        "timeframe": status.timeframe,
        "consumed_count": status.consumed_count,
        "produced_count": status.produced_count,
        "last_processed_at": status.last_processed_at.isoformat() if status.last_processed_at else None,
        "message": status.message,
        "status": "ok" if status.connected else "degraded",
    }


@app.get("/indicator-engine/status")
def indicator_status() -> dict[str, str | bool | int | None]:
    status = build_indicator_engine_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "connected": status.connected,
        "source_topic": status.source_topic,
        "target_topic": status.target_topic,
        "timeframe": status.timeframe,
        "consumed_count": status.consumed_count,
        "produced_count": status.produced_count,
        "last_processed_at": status.last_processed_at.isoformat() if status.last_processed_at else None,
        "message": status.message,
    }


@app.post("/indicator-engine/consume-once")
def consume_once() -> dict[str, int | str]:
    service = build_indicator_engine_service()
    produced_count = service.consume_and_calculate_once()
    return {
        "service": "indicator_engine",
        "produced_count": produced_count,
        "message": "Closed bars consumed and indicators produced",
    }
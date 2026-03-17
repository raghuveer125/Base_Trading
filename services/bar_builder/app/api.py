from fastapi import FastAPI

from services.bar_builder.app.cache_writer import BarBuilderCacheWriter
from services.bar_builder.app.processor import BarBuilderProcessor
from services.bar_builder.app.publisher import BarPublisher
from services.bar_builder.app.replay_api import router as replay_router
from services.bar_builder.app.repository import ClosedBarRepository
from services.bar_builder.app.service import BarBuilderService
from services.bar_builder.app.state_store import InMemoryBarStateStore
from shared.config.settings import get_settings
from shared.kafka.consumer import KafkaEventConsumer
from shared.kafka.producer import KafkaEventProducer
from shared.postgres.client import PostgresClient
from shared.redis.client import RedisStateClient

app = FastAPI(title="bar_builder", version="0.1.0")
app.include_router(replay_router)

_state_store = InMemoryBarStateStore()


def build_bar_builder_service() -> BarBuilderService:
    settings = get_settings()

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
        state_store=_state_store,
        cache_writer=BarBuilderCacheWriter(
            settings=settings,
            redis_client=redis_client,
        ),
        repository=ClosedBarRepository(
            postgres_client=postgres_client,
        ),
    )
    service.connect()
    return service


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    status = build_bar_builder_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "connected": status.connected,
        "source_topic": status.source_topic,
        "target_topic": status.target_topic,
        "closed_topic": status.closed_topic,
        "timeframe": status.timeframe,
        "consumed_count": status.consumed_count,
        "produced_count": status.produced_count,
        "closed_count": status.closed_count,
        "open_bar_count": status.open_bar_count,
        "last_processed_at": status.last_processed_at.isoformat() if status.last_processed_at else None,
        "message": status.message,
        "status": "ok" if status.connected else "degraded",
    }


@app.get("/bar-builder/status")
def bar_builder_status() -> dict[str, str | bool | int | None]:
    status = build_bar_builder_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "connected": status.connected,
        "source_topic": status.source_topic,
        "target_topic": status.target_topic,
        "closed_topic": status.closed_topic,
        "timeframe": status.timeframe,
        "consumed_count": status.consumed_count,
        "produced_count": status.produced_count,
        "closed_count": status.closed_count,
        "open_bar_count": status.open_bar_count,
        "last_processed_at": status.last_processed_at.isoformat() if status.last_processed_at else None,
        "message": status.message,
    }


@app.post("/bar-builder/consume-once")
def consume_once() -> dict[str, int | str]:
    service = build_bar_builder_service()
    built_count = service.consume_and_build_once()
    status = service.get_status()
    return {
        "service": "bar_builder",
        "built_count": built_count,
        "closed_count": status.closed_count,
        "open_bar_count": status.open_bar_count,
        "message": "Tick records consumed and bar records produced",
    }
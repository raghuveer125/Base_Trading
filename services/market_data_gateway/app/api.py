from fastapi import FastAPI

from services.market_data_gateway.app.cache_writer import MarketDataCacheWriter
from services.market_data_gateway.app.feed_stub import StubPriceFeed
from services.market_data_gateway.app.normalizer import MarketDataNormalizer
from services.market_data_gateway.app.publisher import MarketDataPublisher
from services.market_data_gateway.app.service import MarketDataGatewayService
from shared.config.settings import get_settings
from shared.kafka.admin import KafkaTopicAdmin
from shared.kafka.producer import KafkaEventProducer
from shared.redis.client import RedisStateClient

app = FastAPI(title="market_data_gateway", version="0.1.0")


def build_gateway_service() -> MarketDataGatewayService:
    settings = get_settings()

    topic_admin = KafkaTopicAdmin(settings=settings)
    topic_admin.connect()
    topic_admin.ensure_topic(settings.kafka_topic_ticks)
    topic_admin.close()

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
    return service


@app.get("/health")
def health() -> dict[str, str | bool | None | list[str]]:
    status = build_gateway_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "connected": status.connected,
        "subscribed_symbols": status.subscribed_symbols,
        "last_emit_at": status.last_emit_at.isoformat() if status.last_emit_at else None,
        "message": status.message,
        "status": "ok" if status.connected else "degraded",
    }


@app.post("/gateway/emit-once")
def emit_once() -> dict[str, int | str]:
    service = build_gateway_service()
    emitted = service.emit_once()
    return {
        "service": "market_data_gateway",
        "emitted_count": emitted,
        "message": "Ticks emitted successfully",
    }


@app.get("/gateway/status")
def gateway_status() -> dict[str, str | bool | None | list[str]]:
    status = build_gateway_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "connected": status.connected,
        "subscribed_symbols": status.subscribed_symbols,
        "last_emit_at": status.last_emit_at.isoformat() if status.last_emit_at else None,
        "message": status.message,
    }
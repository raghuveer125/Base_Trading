from fastapi import APIRouter

from services.indicator_engine.app.replay_service import IndicatorReplayService
from services.indicator_engine.app.repository import IndicatorRepository
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

router = APIRouter()


def build_replay_service() -> IndicatorReplayService:
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()
    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()
    return IndicatorReplayService(repository=repository)


@router.get("/indicator-engine/replay/status")
def replay_status() -> dict[str, str | int | bool]:
    status = build_replay_service().get_status()
    return {
        "service": status.service,
        "replay_ready": status.replay_ready,
        "source_table": status.source_table,
        "records_loaded": status.records_loaded,
        "message": status.message,
    }


@router.get("/indicator-engine/replay/indicators")
def replay_indicators() -> dict[str, object]:
    service = build_replay_service()
    indicators = service.load_indicators()

    return {
        "service": "indicator_engine",
        "record_count": len(indicators),
        "records": [indicator.model_dump(mode="json") for indicator in indicators],
    }
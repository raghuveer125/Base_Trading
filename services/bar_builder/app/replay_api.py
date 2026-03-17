from fastapi import APIRouter

from services.bar_builder.app.replay_service import ClosedBarReplayService
from services.bar_builder.app.repository import ClosedBarRepository
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

router = APIRouter()


def build_replay_service() -> ClosedBarReplayService:
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()
    repository = ClosedBarRepository(postgres_client=postgres_client)
    repository.ensure_table()
    return ClosedBarReplayService(repository=repository)


@router.get("/bar-builder/replay/status")
def replay_status() -> dict[str, str | int | bool]:
    status = build_replay_service().get_status()
    return {
        "service": status.service,
        "replay_ready": status.replay_ready,
        "source_table": status.source_table,
        "records_loaded": status.records_loaded,
        "message": status.message,
    }


@router.get("/bar-builder/replay/closed-bars")
def replay_closed_bars() -> dict[str, object]:
    service = build_replay_service()
    bars = service.load_closed_bars()

    return {
        "service": "bar_builder",
        "record_count": len(bars),
        "records": [bar.model_dump(mode="json") for bar in bars],
    }
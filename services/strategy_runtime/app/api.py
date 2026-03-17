from fastapi import FastAPI

from services.indicator_engine.app.repository import IndicatorRepository
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from services.strategy_runtime.app.service import StrategyRuntimeService
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

app = FastAPI(title="strategy_runtime", version="0.1.0")


def build_strategy_runtime_service() -> StrategyRuntimeService:
    settings = get_settings()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()

    service = StrategyRuntimeService(
        settings=settings,
        replay_reader=IndicatorReplayReader(repository=repository),
        processor=StrategyProcessor(),
    )
    return service


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    status = build_strategy_runtime_service().get_status()
    return {
        "service": status.service,
        "strategy_name": status.strategy_name,
        "mode": status.mode,
        "replay_ready": status.replay_ready,
        "source_table": status.source_table,
        "records_loaded": status.records_loaded,
        "generated_signals": status.generated_signals,
        "last_evaluated_at": status.last_evaluated_at.isoformat() if status.last_evaluated_at else None,
        "message": status.message,
        "status": "ok" if status.replay_ready else "degraded",
    }


@app.get("/strategy-runtime/status")
def strategy_status() -> dict[str, str | bool | int | None]:
    status = build_strategy_runtime_service().get_status()
    return {
        "service": status.service,
        "strategy_name": status.strategy_name,
        "mode": status.mode,
        "replay_ready": status.replay_ready,
        "source_table": status.source_table,
        "records_loaded": status.records_loaded,
        "generated_signals": status.generated_signals,
        "last_evaluated_at": status.last_evaluated_at.isoformat() if status.last_evaluated_at else None,
        "message": status.message,
    }


@app.post("/strategy-runtime/evaluate-once")
def evaluate_once() -> dict[str, object]:
    service = build_strategy_runtime_service()
    signals = service.evaluate_once()
    return {
        "service": "strategy_runtime",
        "signal_count": len(signals),
        "signals": signals,
        "message": "Strategy evaluation completed",
    }
from fastapi import FastAPI

from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.service import RiskService
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

app = FastAPI(title="risk_service", version="0.1.0")


def build_risk_service() -> RiskService:
    settings = get_settings()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()

    service = RiskService(
        settings=settings,
        signal_reader=StrategySignalReader(
            replay_reader=IndicatorReplayReader(repository=repository),
            strategy_processor=StrategyProcessor(),
        ),
        processor=RiskProcessor(settings=settings),
    )
    return service


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    status = build_risk_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "replay_ready": status.replay_ready,
        "source": status.source,
        "signals_loaded": status.signals_loaded,
        "approved_signals": status.approved_signals,
        "rejected_signals": status.rejected_signals,
        "last_evaluated_at": status.last_evaluated_at.isoformat() if status.last_evaluated_at else None,
        "message": status.message,
        "status": "ok" if status.replay_ready else "degraded",
    }


@app.get("/risk-service/status")
def risk_status() -> dict[str, str | bool | int | None]:
    status = build_risk_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "replay_ready": status.replay_ready,
        "source": status.source,
        "signals_loaded": status.signals_loaded,
        "approved_signals": status.approved_signals,
        "rejected_signals": status.rejected_signals,
        "last_evaluated_at": status.last_evaluated_at.isoformat() if status.last_evaluated_at else None,
        "message": status.message,
    }


@app.post("/risk-service/evaluate-once")
def evaluate_once() -> dict[str, object]:
    service = build_risk_service()
    result = service.evaluate_once()
    return {
        "service": "risk_service",
        "approved_count": len(result["approved"]),
        "rejected_count": len(result["rejected"]),
        "approved": result["approved"],
        "rejected": result["rejected"],
        "message": "Risk evaluation completed",
    }
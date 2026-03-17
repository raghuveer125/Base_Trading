from fastapi import FastAPI

from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

app = FastAPI(title="execution_service", version="0.1.0")


def build_execution_service() -> ExecutionService:
    settings = get_settings()

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()

    service = ExecutionService(
        settings=settings,
        signal_reader=ApprovedSignalReader(
            signal_reader=StrategySignalReader(
                replay_reader=IndicatorReplayReader(repository=repository),
                strategy_processor=StrategyProcessor(),
            ),
            risk_processor=RiskProcessor(settings=settings),
        ),
        processor=ExecutionProcessor(settings=settings),
    )
    return service


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    status = build_execution_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "broker": status.broker,
        "replay_ready": status.replay_ready,
        "approved_loaded": status.approved_loaded,
        "orders_prepared": status.orders_prepared,
        "last_prepared_at": status.last_prepared_at.isoformat() if status.last_prepared_at else None,
        "message": status.message,
        "status": "ok" if status.replay_ready else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, str | bool | int | None]:
    status = build_execution_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "broker": status.broker,
        "replay_ready": status.replay_ready,
        "approved_loaded": status.approved_loaded,
        "orders_prepared": status.orders_prepared,
        "last_prepared_at": status.last_prepared_at.isoformat() if status.last_prepared_at else None,
        "message": status.message,
    }


@app.post("/execution-service/prepare-once")
def prepare_once() -> dict[str, object]:
    service = build_execution_service()
    orders = service.prepare_once()
    return {
        "service": "execution_service",
        "order_count": len(orders),
        "orders": orders,
        "message": "Execution preparation completed",
    }
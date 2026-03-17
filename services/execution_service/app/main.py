import asyncio
import os

import uvicorn

from services.execution_service.app.api import app
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.logging.logger import configure_logging, get_logger
from shared.postgres.client import PostgresClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("execution_service")

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

    logger.info(
        "service_started",
        service="execution_service",
        env=settings.app_env,
        mode=settings.execution_service_mode,
        broker=settings.execution_service_broker,
        postgres_enabled=settings.postgres_enabled,
    )

    orders = service.prepare_once()
    postgres_client.close()

    logger.info(
        "execution_prepare_complete",
        service="execution_service",
        order_count=len(orders),
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("execution_service")

    logger.info(
        "execution_service_api_starting",
        service="execution_service",
        env=settings.app_env,
        host=settings.execution_service_api_host,
        port=settings.execution_service_api_port,
        broker=settings.execution_service_broker,
        postgres_enabled=settings.postgres_enabled,
    )

    uvicorn.run(
        app,
        host=settings.execution_service_api_host,
        port=settings.execution_service_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("EXECUTION_SERVICE_MODE", "stub").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
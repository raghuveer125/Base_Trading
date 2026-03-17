import asyncio
import os

import uvicorn

from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.api import app
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.service import RiskService
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.logging.logger import configure_logging, get_logger
from shared.postgres.client import PostgresClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("risk_service")

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

    logger.info(
        "service_started",
        service="risk_service",
        env=settings.app_env,
        mode=settings.risk_service_mode,
        postgres_enabled=settings.postgres_enabled,
        max_open_positions=settings.risk_max_open_positions,
        max_signal_size=settings.risk_max_signal_size,
    )

    result = service.evaluate_once()
    postgres_client.close()

    logger.info(
        "risk_evaluation_complete",
        service="risk_service",
        approved_count=len(result["approved"]),
        rejected_count=len(result["rejected"]),
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("risk_service")

    logger.info(
        "risk_service_api_starting",
        service="risk_service",
        env=settings.app_env,
        host=settings.risk_service_api_host,
        port=settings.risk_service_api_port,
        postgres_enabled=settings.postgres_enabled,
        max_open_positions=settings.risk_max_open_positions,
        max_signal_size=settings.risk_max_signal_size,
    )

    uvicorn.run(
        app,
        host=settings.risk_service_api_host,
        port=settings.risk_service_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("RISK_SERVICE_MODE", "stub").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
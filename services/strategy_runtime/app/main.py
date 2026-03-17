import asyncio
import os

import uvicorn

from services.indicator_engine.app.repository import IndicatorRepository
from services.strategy_runtime.app.api import app
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from services.strategy_runtime.app.service import StrategyRuntimeService
from shared.config.settings import get_settings
from shared.logging.logger import configure_logging, get_logger
from shared.postgres.client import PostgresClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("strategy_runtime")

    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()

    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()

    service = StrategyRuntimeService(
        settings=settings,
        replay_reader=IndicatorReplayReader(repository=repository),
        processor=StrategyProcessor(),
    )

    logger.info(
        "service_started",
        service="strategy_runtime",
        env=settings.app_env,
        mode=settings.strategy_runtime_mode,
        strategy_name=settings.strategy_runtime_name,
        postgres_enabled=settings.postgres_enabled,
    )

    signals = service.evaluate_once()
    postgres_client.close()

    logger.info(
        "strategy_evaluation_complete",
        service="strategy_runtime",
        signal_count=len(signals),
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("strategy_runtime")

    logger.info(
        "strategy_runtime_api_starting",
        service="strategy_runtime",
        env=settings.app_env,
        host=settings.strategy_runtime_api_host,
        port=settings.strategy_runtime_api_port,
        strategy_name=settings.strategy_runtime_name,
        postgres_enabled=settings.postgres_enabled,
    )

    uvicorn.run(
        app,
        host=settings.strategy_runtime_api_host,
        port=settings.strategy_runtime_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("STRATEGY_RUNTIME_MODE", "stub").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
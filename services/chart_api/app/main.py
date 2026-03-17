from shared.config.settings import get_settings
from shared.logging.logger import configure_logging, get_logger


def main() -> None:
    configure_logging()
    settings = get_settings()
    logger = get_logger("chart_api")
    logger.info(
        "service_started",
        service="chart_api",
        env=settings.app_env,
    )


if __name__ == "__main__":
    main()
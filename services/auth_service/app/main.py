import os

import uvicorn

from shared.config.settings import get_settings
from shared.logging.logger import configure_logging, get_logger
from services.auth_service.app.api import app
from services.auth_service.app.provider import FyersAuthProvider
from services.auth_service.app.service import AuthService
from services.auth_service.app.session_store import SessionStore


def run_bootstrap_mode() -> None:
    settings = get_settings()
    logger = get_logger("auth_service")

    provider = FyersAuthProvider(settings=settings)
    session_store = SessionStore(file_path=settings.auth_session_file)
    auth_service = AuthService(
        settings=settings,
        provider=provider,
        session_store=session_store,
    )

    try:
        session = auth_service.bootstrap_session()
        status = auth_service.get_status()
        logger.info(
            "service_started",
            service="auth_service",
            env=settings.app_env,
            authenticated=status.authenticated,
            session_present=status.session_present,
            token_expired=status.token_expired,
        )
        logger.info(
            "auth_session_ready",
            service="auth_service",
            env=settings.app_env,
            token_type=session.token_type,
        )
    except Exception as exc:
        logger.error(
            "auth_startup_failed",
            service="auth_service",
            env=settings.app_env,
            error=str(exc),
        )
        raise


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("auth_service")

    logger.info(
        "auth_api_starting",
        service="auth_service",
        env=settings.app_env,
        host="127.0.0.1",
        port=8001,
    )

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8001,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("AUTH_SERVICE_MODE", "bootstrap").strip().lower()

    if mode == "api":
        run_api_mode()
        return

    run_bootstrap_mode()


if __name__ == "__main__":
    main()
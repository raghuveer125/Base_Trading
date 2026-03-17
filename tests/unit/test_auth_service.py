from pathlib import Path

from shared.config.settings import Settings
from services.auth_service.app.provider import FyersAuthProvider
from services.auth_service.app.service import AuthService
from services.auth_service.app.session_store import SessionStore


def build_settings(session_file: Path, access_token: str = "test_token") -> Settings:
    return Settings(
        APP_ENV="local",
        APP_NAME="projectX",
        LOG_LEVEL="INFO",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="projectx",
        POSTGRES_USER="projectx",
        POSTGRES_PASSWORD="changeme",
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        FYERS_CLIENT_ID="client_id",
        FYERS_SECRET_KEY="secret_key",
        FYERS_REDIRECT_URI="http://localhost/callback",
        FYERS_ACCESS_TOKEN=access_token,
        AUTH_SESSION_FILE=str(session_file),
        AUTH_REQUEST_TIMEOUT_SECONDS=10,
        AUTH_VALIDATE_ON_STARTUP=False,
    )


def test_bootstrap_session_creates_file(tmp_path: Path) -> None:
    session_file = tmp_path / "session.json"
    settings = build_settings(session_file=session_file)
    provider = FyersAuthProvider(settings=settings)
    session_store = SessionStore(file_path=str(session_file))
    auth_service = AuthService(
        settings=settings,
        provider=provider,
        session_store=session_store,
    )

    session = auth_service.bootstrap_session()

    assert session.access_token == "test_token"
    assert session_store.exists() is True


def test_get_status_returns_valid_after_bootstrap(tmp_path: Path) -> None:
    session_file = tmp_path / "session.json"
    settings = build_settings(session_file=session_file)
    provider = FyersAuthProvider(settings=settings)
    session_store = SessionStore(file_path=str(session_file))
    auth_service = AuthService(
        settings=settings,
        provider=provider,
        session_store=session_store,
    )

    auth_service.bootstrap_session()
    status = auth_service.get_status()

    assert status.service == "auth_service"
    assert status.authenticated is True
    assert status.session_present is True
    assert status.token_expired is False


def test_bootstrap_session_raises_when_access_token_missing(tmp_path: Path) -> None:
    session_file = tmp_path / "session.json"
    settings = build_settings(session_file=session_file, access_token="")
    provider = FyersAuthProvider(settings=settings)
    session_store = SessionStore(file_path=str(session_file))
    auth_service = AuthService(
        settings=settings,
        provider=provider,
        session_store=session_store,
    )

    try:
        auth_service.bootstrap_session()
    except RuntimeError as exc:
        assert str(exc) == "FYERS_ACCESS_TOKEN is missing"
    else:
        raise AssertionError("Expected RuntimeError for missing access token")
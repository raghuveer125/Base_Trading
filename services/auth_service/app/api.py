from fastapi import FastAPI

from shared.config.settings import get_settings
from services.auth_service.app.provider import FyersAuthProvider
from services.auth_service.app.service import AuthService
from services.auth_service.app.session_store import SessionStore

app = FastAPI(title="auth_service", version="0.1.0")


def build_auth_service() -> AuthService:
    settings = get_settings()
    provider = FyersAuthProvider(settings=settings)
    session_store = SessionStore(file_path=settings.auth_session_file)
    return AuthService(
        settings=settings,
        provider=provider,
        session_store=session_store,
    )


@app.get("/health")
def health() -> dict[str, str | bool]:
    settings = get_settings()
    auth_service = build_auth_service()
    status = auth_service.get_status()

    return {
        "service": "auth_service",
        "env": settings.app_env,
        "status": "ok" if status.authenticated else "degraded",
        "authenticated": status.authenticated,
        "session_present": status.session_present,
        "token_expired": status.token_expired,
        "message": status.message,
    }


@app.get("/auth/status")
def auth_status() -> dict[str, str | bool | None]:
    status = build_auth_service().get_status()
    return {
        "service": status.service,
        "authenticated": status.authenticated,
        "session_present": status.session_present,
        "token_expired": status.token_expired,
        "last_validated_at": status.last_validated_at.isoformat() if status.last_validated_at else None,
        "message": status.message,
    }


@app.post("/auth/bootstrap")
def auth_bootstrap() -> dict[str, str | bool | None]:
    auth_service = build_auth_service()
    session = auth_service.bootstrap_session()
    status = auth_service.get_status()

    return {
        "service": "auth_service",
        "authenticated": status.authenticated,
        "session_present": status.session_present,
        "token_expired": status.token_expired,
        "token_type": session.token_type,
        "message": status.message,
    }
from __future__ import annotations

from datetime import UTC, datetime

from shared.config.settings import Settings
from services.auth_service.app.models import AuthSession, AuthStatus
from services.auth_service.app.provider import FyersAuthProvider
from services.auth_service.app.session_store import SessionStore


class AuthService:
    def __init__(
        self,
        settings: Settings,
        provider: FyersAuthProvider,
        session_store: SessionStore,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._session_store = session_store

    def bootstrap_session(self) -> AuthSession:
        stored_session = self._session_store.load()
        if stored_session and self._provider.validate_session(stored_session):
            return stored_session

        session = self._provider.create_session_from_env()
        self._session_store.save(session)
        return session

    def get_status(self) -> AuthStatus:
        session = self._session_store.load()
        now = datetime.now(UTC)

        if session is None:
            return AuthStatus(
                service="auth_service",
                authenticated=False,
                session_present=False,
                token_expired=False,
                last_validated_at=now,
                message="No stored auth session found",
            )

        is_valid = self._provider.validate_session(session)
        return AuthStatus(
            service="auth_service",
            authenticated=is_valid,
            session_present=True,
            token_expired=session.is_expired,
            last_validated_at=now,
            message="Auth session valid" if is_valid else "Auth session invalid",
        )
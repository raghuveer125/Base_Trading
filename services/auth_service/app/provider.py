from __future__ import annotations

from shared.config.settings import Settings
from services.auth_service.app.models import AuthSession


class FyersAuthProvider:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_session_from_env(self) -> AuthSession:
        if not self._settings.fyers_access_token:
            raise RuntimeError("FYERS_ACCESS_TOKEN is missing")
        return AuthSession.from_access_token(
            access_token=self._settings.fyers_access_token,
            expires_in_seconds=None,
        )

    def validate_session(self, session: AuthSession) -> bool:
        if not session.access_token.strip():
            return False
        if session.is_expired:
            return False
        return session.is_valid
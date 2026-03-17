from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class AuthSession(BaseModel):
    access_token: str = Field(min_length=1)
    token_type: str = "Bearer"
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    is_valid: bool = True

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        return utc_now() >= self.expires_at

    @classmethod
    def from_access_token(
        cls,
        access_token: str,
        expires_in_seconds: int | None = None,
    ) -> "AuthSession":
        expires_at = None
        if expires_in_seconds is not None:
            expires_at = utc_now() + timedelta(seconds=expires_in_seconds)
        return cls(
            access_token=access_token,
            expires_at=expires_at,
            is_valid=True,
        )


class AuthStatus(BaseModel):
    service: str
    authenticated: bool
    session_present: bool
    token_expired: bool
    last_validated_at: datetime | None = None
    message: str
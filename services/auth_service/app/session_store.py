from __future__ import annotations

import json
from pathlib import Path

from services.auth_service.app.models import AuthSession


class SessionStore:
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)

    def save(self, session: AuthSession) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(session.model_dump_json(indent=2), encoding="utf-8")

    def load(self) -> AuthSession | None:
        if not self._path.exists():
            return None
        raw = self._path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return AuthSession.model_validate(data)

    def exists(self) -> bool:
        return self._path.exists()

    def delete(self) -> None:
        if self._path.exists():
            self._path.unlink()
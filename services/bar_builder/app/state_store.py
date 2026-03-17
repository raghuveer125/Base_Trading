from __future__ import annotations

from collections.abc import Iterable

from shared.models import BarEvent


class InMemoryBarStateStore:
    def __init__(self) -> None:
        self._bars: dict[str, BarEvent] = {}

    def get(self, key: str) -> BarEvent | None:
        return self._bars.get(key)

    def set(self, key: str, value: BarEvent) -> None:
        self._bars[key] = value

    def pop(self, key: str) -> BarEvent | None:
        return self._bars.pop(key, None)

    def items(self) -> Iterable[tuple[str, BarEvent]]:
        return self._bars.items()

    def values(self) -> Iterable[BarEvent]:
        return self._bars.values()

    def size(self) -> int:
        return len(self._bars)
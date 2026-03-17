from __future__ import annotations

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class RiskProcessor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("risk_service.processor")

    def apply_risk(self, signals: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        approved: list[dict[str, str]] = []
        rejected: list[dict[str, str]] = []

        for signal in signals:
            if signal["signal"] == "HOLD":
                rejected.append({**signal, "reason": "hold_signal"})
                continue

            if len(approved) >= self._settings.risk_max_open_positions:
                rejected.append({**signal, "reason": "max_open_positions_reached"})
                continue

            approved.append({**signal, "size": str(self._settings.risk_max_signal_size)})

        self._logger.info(
            "risk_applied",
            approved_count=len(approved),
            rejected_count=len(rejected),
        )
        return approved, rejected
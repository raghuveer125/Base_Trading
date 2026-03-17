from __future__ import annotations

from datetime import UTC, datetime

from services.risk_service.app.models import RiskServiceStatus
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from shared.config.settings import Settings


class RiskService:
    def __init__(
        self,
        settings: Settings,
        signal_reader: StrategySignalReader,
        processor: RiskProcessor,
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._approved_signals = 0
        self._rejected_signals = 0
        self._last_evaluated_at: datetime | None = None

    def evaluate_once(self) -> dict[str, object]:
        signals = self._signal_reader.load_signals()
        approved, rejected = self._processor.apply_risk(signals)
        self._approved_signals = len(approved)
        self._rejected_signals = len(rejected)
        self._last_evaluated_at = datetime.now(UTC)

        return {
            "approved": approved,
            "rejected": rejected,
        }

    def get_status(self) -> RiskServiceStatus:
        signals = self._signal_reader.load_signals()
        return RiskServiceStatus(
            service="risk_service",
            mode=self._settings.risk_service_mode,
            replay_ready=True,
            source="strategy_runtime_replay",
            signals_loaded=len(signals),
            approved_signals=self._approved_signals,
            rejected_signals=self._rejected_signals,
            last_evaluated_at=self._last_evaluated_at,
            message="Risk service ready",
        )
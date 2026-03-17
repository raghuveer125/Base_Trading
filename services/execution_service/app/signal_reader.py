from __future__ import annotations

from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from shared.logging.logger import get_logger


class ApprovedSignalReader:
    def __init__(
        self,
        signal_reader: StrategySignalReader,
        risk_processor: RiskProcessor,
    ) -> None:
        self._signal_reader = signal_reader
        self._risk_processor = risk_processor
        self._logger = get_logger("execution_service.signal_reader")

    def load_approved_signals(self) -> list[dict[str, str]]:
        signals = self._signal_reader.load_signals()
        approved, _ = self._risk_processor.apply_risk(signals)
        self._logger.info(
            "approved_signals_loaded_for_execution",
            approved_count=len(approved),
        )
        return approved
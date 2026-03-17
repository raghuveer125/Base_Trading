from __future__ import annotations

from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.logging.logger import get_logger


class StrategySignalReader:
    def __init__(
        self,
        replay_reader: IndicatorReplayReader,
        strategy_processor: StrategyProcessor,
    ) -> None:
        self._replay_reader = replay_reader
        self._strategy_processor = strategy_processor
        self._logger = get_logger("risk_service.signal_reader")

    def load_signals(self) -> list[dict[str, str]]:
        indicators = self._replay_reader.load_indicators()
        signals = self._strategy_processor.evaluate(indicators)
        self._logger.info(
            "signals_loaded_for_risk",
            signal_count=len(signals),
        )
        return signals
from __future__ import annotations

from datetime import UTC, datetime

from services.strategy_runtime.app.models import StrategyRuntimeStatus
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import Settings


class StrategyRuntimeService:
    def __init__(
        self,
        settings: Settings,
        replay_reader: IndicatorReplayReader,
        processor: StrategyProcessor,
    ) -> None:
        self._settings = settings
        self._replay_reader = replay_reader
        self._processor = processor
        self._generated_signals = 0
        self._last_evaluated_at: datetime | None = None

    def evaluate_once(self) -> list[dict[str, str]]:
        indicators = self._replay_reader.load_indicators()
        signals = self._processor.evaluate(indicators)
        self._generated_signals = len(signals)
        self._last_evaluated_at = datetime.now(UTC)
        return signals

    def get_status(self) -> StrategyRuntimeStatus:
        indicators = self._replay_reader.load_indicators()
        return StrategyRuntimeStatus(
            service="strategy_runtime",
            strategy_name=self._settings.strategy_runtime_name,
            mode=self._settings.strategy_runtime_mode,
            replay_ready=True,
            source_table="indicators_1m",
            records_loaded=len(indicators),
            generated_signals=self._generated_signals,
            last_evaluated_at=self._last_evaluated_at,
            message="Strategy runtime ready",
        )
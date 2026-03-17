from __future__ import annotations

from shared.logging.logger import get_logger
from shared.models import IndicatorEvent


class StrategyProcessor:
    def __init__(self) -> None:
        self._logger = get_logger("strategy_runtime.processor")

    def evaluate(self, indicators: list[IndicatorEvent]) -> list[dict[str, str]]:
        signals: list[dict[str, str]] = []

        for indicator in indicators:
            signal = "HOLD"
            if indicator.payload.values.ema_7 > indicator.payload.values.sma_5:
                signal = "BUY"
            elif indicator.payload.values.ema_7 < indicator.payload.values.sma_5:
                signal = "SELL"

            signals.append(
                {
                    "symbol": indicator.payload.symbol,
                    "timeframe": indicator.payload.timeframe,
                    "bar_start_time": indicator.payload.bar_start_time.isoformat(),
                    "signal": signal,
                }
            )

        self._logger.info(
            "strategy_signals_generated",
            signal_count=len(signals),
        )
        return signals
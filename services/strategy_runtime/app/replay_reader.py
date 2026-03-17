from __future__ import annotations

from services.indicator_engine.app.repository import IndicatorRepository
from shared.logging.logger import get_logger
from shared.models import IndicatorEvent, IndicatorValues


class IndicatorReplayReader:
    def __init__(self, repository: IndicatorRepository) -> None:
        self._repository = repository
        self._logger = get_logger("strategy_runtime.replay_reader")

    def load_indicators(self) -> list[IndicatorEvent]:
        rows = self._repository.fetch_indicators()
        if rows is None:
            return []

        indicators: list[IndicatorEvent] = []
        for row in rows:
            indicators.append(
                IndicatorEvent.create(
                    source="strategy_runtime_replay",
                    symbol=row[0],
                    exchange=row[1],
                    timeframe=row[2],
                    bar_start_time=row[3],
                    values=IndicatorValues(
                        ema_7=row[4],
                        ema_9=row[5],
                        sma_3=row[6],
                        sma_5=row[7],
                    ),
                )
            )

        self._logger.info(
            "indicators_loaded_for_strategy_runtime",
            count=len(indicators),
        )
        return indicators
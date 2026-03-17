from __future__ import annotations

from services.bar_builder.app.replay_models import ReplayStatus
from services.bar_builder.app.repository import ClosedBarRepository
from shared.logging.logger import get_logger
from shared.models import BarEvent


class ClosedBarReplayService:
    def __init__(self, repository: ClosedBarRepository) -> None:
        self._repository = repository
        self._logger = get_logger("bar_builder.replay_service")

    def load_closed_bars(self) -> list[BarEvent]:
        rows = self._repository.fetch_closed_bars()
        if rows is None:
            return []

        bars: list[BarEvent] = []
        for row in rows:
            bars.append(
                BarEvent.create(
                    source="bar_builder_replay",
                    symbol=row[0],
                    exchange=row[1],
                    timeframe=row[2],
                    bar_start_time=row[3],
                    bar_end_time=row[4],
                    open_price=row[5],
                    high_price=row[6],
                    low_price=row[7],
                    close_price=row[8],
                    volume=row[9],
                    source_detail=row[10],
                    revision=row[11],
                )
            )

        self._logger.info(
            "closed_bars_loaded_for_replay",
            count=len(bars),
        )
        return bars

    def get_status(self) -> ReplayStatus:
        rows = self._repository.fetch_closed_bars()
        count = 0 if rows is None else len(rows)
        return ReplayStatus(
            service="bar_builder",
            replay_ready=True,
            source_table="closed_bars_1m",
            records_loaded=count,
            message="Replay source ready",
        )
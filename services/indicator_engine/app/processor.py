from __future__ import annotations

from decimal import Decimal

from shared.models import IndicatorEvent, IndicatorValues


class IndicatorProcessor:
    def build_indicator_from_bar(self, bar_event: dict, timeframe: str) -> IndicatorEvent:
        payload = bar_event["payload"]
        close_price = Decimal(str(payload["close"]))

        values = IndicatorValues(
            ema_7=close_price,
            ema_9=close_price,
            sma_3=close_price,
            sma_5=close_price,
        )

        return IndicatorEvent.create(
            source="indicator_engine",
            symbol=payload["symbol"],
            exchange=payload["exchange"],
            timeframe=timeframe,
            bar_start_time=payload["bar_start_time"],
            values=values,
        )
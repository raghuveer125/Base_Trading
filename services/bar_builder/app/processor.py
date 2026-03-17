from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from shared.models import BarEvent


class BarBuilderProcessor:
    def build_bar_key(self, symbol: str, timeframe: str, bar_start_time: datetime) -> str:
        return f"{symbol}|{timeframe}|{bar_start_time.astimezone(UTC).isoformat()}"

    def get_bar_window(self, tick_event: dict) -> tuple[datetime, datetime]:
        payload = tick_event["payload"]
        last_trade_time = datetime.fromisoformat(payload["last_trade_time"])
        bar_start_time = last_trade_time.replace(second=0, microsecond=0)
        bar_end_time = bar_start_time + timedelta(minutes=1)
        return bar_start_time.astimezone(UTC), bar_end_time.astimezone(UTC)

    def create_bar_from_tick(self, tick_event: dict, timeframe: str) -> BarEvent:
        payload = tick_event["payload"]
        bar_start_time, bar_end_time = self.get_bar_window(tick_event)
        price = Decimal(str(payload["last_traded_price"]))

        return BarEvent.create(
            source="bar_builder",
            symbol=payload["symbol"],
            exchange=payload["exchange"],
            timeframe=timeframe,
            bar_start_time=bar_start_time,
            bar_end_time=bar_end_time,
            open_price=price,
            high_price=price,
            low_price=price,
            close_price=price,
            volume=int(payload.get("last_traded_quantity") or 0),
            source_detail="tick_to_bar_stateful",
            revision=1,
        )

    def update_existing_bar(self, existing_bar: BarEvent, tick_event: dict) -> BarEvent:
        payload = tick_event["payload"]
        price = Decimal(str(payload["last_traded_price"]))
        quantity = int(payload.get("last_traded_quantity") or 0)

        return BarEvent.create(
            source="bar_builder",
            symbol=existing_bar.payload.symbol,
            exchange=existing_bar.payload.exchange,
            timeframe=existing_bar.payload.timeframe,
            bar_start_time=existing_bar.payload.bar_start_time,
            bar_end_time=existing_bar.payload.bar_end_time,
            open_price=existing_bar.payload.open,
            high_price=max(existing_bar.payload.high, price),
            low_price=min(existing_bar.payload.low, price),
            close_price=price,
            volume=existing_bar.payload.volume + quantity,
            source_detail="tick_to_bar_stateful",
            revision=existing_bar.payload.revision,
        )
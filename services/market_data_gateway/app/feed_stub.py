from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal


class StubPriceFeed:
    def __init__(self) -> None:
        self._counter = 0

    def next_price(self, symbol: str) -> Decimal:
        self._counter += 1

        if symbol == "NSE:SBIN-EQ":
            return Decimal("820.00") + Decimal(self._counter) / Decimal("10")
        if symbol == "NSE:RELIANCE-EQ":
            return Decimal("2950.00") + Decimal(self._counter) / Decimal("10")
        return Decimal("100.00") + Decimal(self._counter) / Decimal("10")

    def next_trade_time(self) -> datetime:
        return datetime.now(UTC)
from __future__ import annotations

from shared.config.settings import Settings
from shared.logging.logger import get_logger


class ExecutionProcessor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("execution_service.processor")

    def prepare_orders(self, approved_signals: list[dict[str, str]]) -> list[dict[str, str]]:
        orders: list[dict[str, str]] = []

        for signal in approved_signals:
            side = "BUY" if signal["signal"] == "BUY" else "SELL"
            orders.append(
                {
                    "symbol": signal["symbol"],
                    "timeframe": signal["timeframe"],
                    "bar_start_time": signal["bar_start_time"],
                    "side": side,
                    "quantity": signal["size"],
                    "broker": self._settings.execution_service_broker,
                    "status": "prepared",
                }
            )

        self._logger.info(
            "execution_orders_prepared",
            order_count=len(orders),
        )
        return orders
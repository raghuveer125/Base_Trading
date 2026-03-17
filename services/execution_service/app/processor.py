from __future__ import annotations

from hashlib import sha256

from services.execution_service.app.models import BrokerPlaceOrderRequest
from shared.config.settings import Settings
from shared.logging.logger import get_logger


class ExecutionProcessor:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("execution_service.processor")

    def prepare_orders(self, approved_signals: list[dict[str, str]]) -> list[dict[str, str]]:
        orders: list[dict[str, str]] = []
        for signal in approved_signals:
            signal_value = signal["signal"].strip().upper()
            side = "BUY" if signal_value == "BUY" else "SELL"
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

    def build_idempotency_key(self, prepared_order: dict[str, str]) -> str:
        raw = "|".join(
            [
                prepared_order["symbol"],
                prepared_order["side"],
                str(prepared_order["quantity"]),
                prepared_order["timeframe"],
                prepared_order["bar_start_time"],
                self._settings.execution_service_broker,
            ]
        )
        return sha256(raw.encode("utf-8")).hexdigest()[:24]

    def build_broker_request(self, prepared_order: dict[str, str]) -> BrokerPlaceOrderRequest:
        request = BrokerPlaceOrderRequest(
            symbol=prepared_order["symbol"],
            side=prepared_order["side"],
            quantity=int(prepared_order["quantity"]),
            order_type="MARKET",
            product="INTRADAY",
            validity="DAY",
            strategy_name="strategy_runtime_stub",
            correlation_id=(
                f"{prepared_order['symbol']}|"
                f"{prepared_order['timeframe']}|"
                f"{prepared_order['bar_start_time']}"
            ),
            idempotency_key=self.build_idempotency_key(prepared_order),
            source_bar_time=prepared_order["bar_start_time"],
        )
        self._logger.info(
            "broker_order_request_built",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )
        return request

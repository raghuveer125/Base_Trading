from __future__ import annotations

from datetime import UTC, datetime

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.models import BrokerHealth, BrokerPlaceOrderResponse, ExecutionServiceStatus
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.signal_reader import ApprovedSignalReader
from shared.config.settings import Settings


class ExecutionService:
    def __init__(
        self,
        settings: Settings,
        signal_reader: ApprovedSignalReader,
        processor: ExecutionProcessor,
        broker_adapter: BrokerAdapter,
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._broker_adapter = broker_adapter
        self._orders_prepared = 0
        self._last_prepared_at: datetime | None = None

    def prepare_once(self) -> list[dict[str, str]]:
        approved_signals = self._signal_reader.load_approved_signals()
        orders = self._processor.prepare_orders(approved_signals)
        self._orders_prepared = len(orders)
        self._last_prepared_at = datetime.now(UTC)
        return orders

    def get_broker_health(self) -> BrokerHealth:
        return self._broker_adapter.health_check()

    def place_first_prepared_order_once(self) -> BrokerPlaceOrderResponse:
        orders = self.prepare_once()
        if not orders:
            return BrokerPlaceOrderResponse(
                broker=self._settings.execution_service_broker,
                adapter="fyers",
                accepted=False,
                status="empty",
                external_order_id=None,
                message="No approved signals available for broker submission",
            )
        request = self._processor.build_broker_request(orders[0])
        return self._broker_adapter.place_order(request)

    def get_status(self) -> ExecutionServiceStatus:
        approved = self._signal_reader.load_approved_signals()
        broker_health = self._broker_adapter.health_check()
        return ExecutionServiceStatus(
            service="execution_service",
            mode=self._settings.execution_service_mode,
            broker=self._settings.execution_service_broker,
            broker_adapter=broker_health.adapter,
            broker_mode=broker_health.mode,
            broker_ready=broker_health.ready,
            replay_ready=True,
            approved_loaded=len(approved),
            orders_prepared=self._orders_prepared,
            last_prepared_at=self._last_prepared_at,
            message="Execution service ready",
        )

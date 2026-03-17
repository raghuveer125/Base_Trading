from __future__ import annotations

from datetime import UTC, datetime

from services.execution_service.app.models import ExecutionServiceStatus
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.signal_reader import ApprovedSignalReader
from shared.config.settings import Settings


class ExecutionService:
    def __init__(
        self,
        settings: Settings,
        signal_reader: ApprovedSignalReader,
        processor: ExecutionProcessor,
    ) -> None:
        self._settings = settings
        self._signal_reader = signal_reader
        self._processor = processor
        self._orders_prepared = 0
        self._last_prepared_at: datetime | None = None

    def prepare_once(self) -> list[dict[str, str]]:
        approved_signals = self._signal_reader.load_approved_signals()
        orders = self._processor.prepare_orders(approved_signals)
        self._orders_prepared = len(orders)
        self._last_prepared_at = datetime.now(UTC)
        return orders

    def get_status(self) -> ExecutionServiceStatus:
        approved = self._signal_reader.load_approved_signals()
        return ExecutionServiceStatus(
            service="execution_service",
            mode=self._settings.execution_service_mode,
            broker=self._settings.execution_service_broker,
            replay_ready=True,
            approved_loaded=len(approved),
            orders_prepared=self._orders_prepared,
            last_prepared_at=self._last_prepared_at,
            message="Execution service ready",
        )
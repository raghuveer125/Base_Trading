from __future__ import annotations

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.brokers.fyers_adapter import FyersBrokerAdapter
from shared.config.settings import Settings


def build_broker_adapter(settings: Settings) -> BrokerAdapter:
    broker = settings.execution_service_broker.strip().lower()
    if broker in {"fyers", "fyers_stub", "fyers_live"}:
        return FyersBrokerAdapter(settings=settings)
    raise ValueError(f"Unsupported execution broker: {settings.execution_service_broker}")

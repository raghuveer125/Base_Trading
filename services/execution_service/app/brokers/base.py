from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from services.execution_service.app.models import BrokerHealth, BrokerPlaceOrderRequest, BrokerPlaceOrderResponse


class BrokerAdapter(Protocol):
    def adapter_name(self) -> str:
        ...

    def is_live(self) -> bool:
        ...

    def health_check(self) -> BrokerHealth:
        ...

    def place_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        ...


@dataclass(slots=True)
class BrokerCapabilities:
    supports_live_orders: bool
    supports_modify: bool
    supports_cancel: bool
    supports_websocket_updates: bool

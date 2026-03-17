from __future__ import annotations

from decimal import Decimal

from services.market_data_gateway.app.models import RawMarketPacket
from shared.models import TickEvent
from shared.utils import normalize_symbol


class MarketDataNormalizer:
    def normalize_tick(self, packet: RawMarketPacket) -> TickEvent:
        return TickEvent.create(
            source="market_data_gateway",
            symbol=normalize_symbol(packet.symbol),
            exchange=packet.exchange,
            last_traded_price=Decimal(packet.ltp),
            last_trade_time=packet.last_trade_time,
            received_at=packet.received_at,
            last_traded_quantity=packet.ltq,
        )
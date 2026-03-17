from __future__ import annotations

from services.market_data_gateway.app.cache_writer import MarketDataCacheWriter
from services.market_data_gateway.app.feed_stub import StubPriceFeed
from services.market_data_gateway.app.models import GatewayStatus, RawMarketPacket
from services.market_data_gateway.app.normalizer import MarketDataNormalizer
from services.market_data_gateway.app.publisher import MarketDataPublisher
from shared.config.settings import Settings


class MarketDataGatewayService:
    def __init__(
        self,
        settings: Settings,
        normalizer: MarketDataNormalizer,
        publisher: MarketDataPublisher,
        stub_feed: StubPriceFeed,
        cache_writer: MarketDataCacheWriter,
    ) -> None:
        self._settings = settings
        self._normalizer = normalizer
        self._publisher = publisher
        self._stub_feed = stub_feed
        self._cache_writer = cache_writer
        self._connected = False
        self._last_emit_at = None

    def connect(self) -> None:
        self._connected = True

    def emit_once(self) -> int:
        if not self._connected:
            raise RuntimeError("Market data gateway is not connected")

        emitted = 0
        for symbol in self._settings.mdg_symbol_list:
            packet = RawMarketPacket(
                symbol=symbol,
                exchange=self._settings.mdg_exchange,
                ltp=self._stub_feed.next_price(symbol),
                ltq=1,
                last_trade_time=self._stub_feed.next_trade_time(),
                raw_payload={"mode": self._settings.mdg_mode},
            )
            event = self._normalizer.normalize_tick(packet)
            self._publisher.publish_tick(event)
            self._cache_writer.cache_tick(event)
            self._last_emit_at = event.payload.received_at
            emitted += 1

        self._cache_writer.cache_status(self.get_status())
        return emitted

    def get_status(self) -> GatewayStatus:
        return GatewayStatus(
            service="market_data_gateway",
            mode=self._settings.mdg_mode,
            connected=self._connected,
            subscribed_symbols=self._settings.mdg_symbol_list,
            last_emit_at=self._last_emit_at,
            message="Gateway connected" if self._connected else "Gateway not connected",
        )
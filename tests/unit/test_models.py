from datetime import UTC, datetime
from decimal import Decimal

from shared.models import BarEvent, HealthEvent, IndicatorEvent, IndicatorValues, TickEvent


def test_health_event_create() -> None:
    event = HealthEvent.create(service="auth_service", status="ok", env="local")
    assert event.meta.event_type == "health"
    assert event.payload.service == "auth_service"
    assert event.payload.status == "ok"
    assert event.payload.env == "local"


def test_tick_event_create() -> None:
    event = TickEvent.create(
        source="market_data_gateway",
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        last_traded_price=Decimal("820.15"),
        last_trade_time=datetime(2026, 3, 17, 9, 15, tzinfo=UTC),
        received_at=datetime(2026, 3, 17, 9, 15, 1, tzinfo=UTC),
        last_traded_quantity=25,
    )
    assert event.meta.event_type == "tick"
    assert event.payload.symbol == "NSE:SBIN-EQ"
    assert event.payload.exchange == "NSE"
    assert event.payload.last_traded_price == Decimal("820.15")


def test_bar_event_create() -> None:
    event = BarEvent.create(
        source="bar_builder",
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        timeframe="1m",
        bar_start_time=datetime(2026, 3, 17, 9, 15, tzinfo=UTC),
        bar_end_time=datetime(2026, 3, 17, 9, 16, tzinfo=UTC),
        open_price=Decimal("820.00"),
        high_price=Decimal("821.00"),
        low_price=Decimal("819.50"),
        close_price=Decimal("820.50"),
        volume=1200,
        source_detail="stream",
        revision=1,
    )
    assert event.meta.event_type == "bar"
    assert event.payload.timeframe == "1m"
    assert event.payload.open == Decimal("820.00")
    assert event.payload.close == Decimal("820.50")


def test_indicator_event_create() -> None:
    event = IndicatorEvent.create(
        source="indicator_engine",
        symbol="NSE:SBIN-EQ",
        exchange="NSE",
        timeframe="1m",
        bar_start_time=datetime(2026, 3, 17, 9, 15, tzinfo=UTC),
        values=IndicatorValues(
            ema_7=Decimal("820.10"),
            ema_9=Decimal("819.90"),
            sma_3=Decimal("820.20"),
            sma_5=Decimal("819.80"),
        ),
    )
    assert event.meta.event_type == "indicator"
    assert event.payload.values.ema_7 == Decimal("820.10")
    assert event.payload.values.sma_5 == Decimal("819.80")
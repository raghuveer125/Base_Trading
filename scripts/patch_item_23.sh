#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app/brokers"
mkdir -p "$ROOT/tests/unit"

cat > "$ROOT/services/execution_service/app/brokers/__init__.py" <<'PY'
from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.brokers.factory import build_broker_adapter

__all__ = ["BrokerAdapter", "build_broker_adapter"]
PY

cat > "$ROOT/services/execution_service/app/brokers/base.py" <<'PY'
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
PY

cat > "$ROOT/services/execution_service/app/brokers/fyers_adapter.py" <<'PY'
from __future__ import annotations

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.models import (
    BrokerHealth,
    BrokerPlaceOrderRequest,
    BrokerPlaceOrderResponse,
)
from shared.config.settings import Settings
from shared.logging.logger import get_logger


class FyersBrokerAdapter(BrokerAdapter):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("execution_service.brokers.fyers")

    def adapter_name(self) -> str:
        return self._settings.execution_service_broker

    def is_live(self) -> bool:
        return self._settings.execution_service_broker.strip().lower() == "fyers_live"

    def health_check(self) -> BrokerHealth:
        has_client_id = bool(self._settings.fyers_client_id.strip())
        has_access_token = bool(self._settings.fyers_access_token.strip())

        ready = has_client_id and has_access_token
        mode = "live" if self.is_live() else "stub"

        message = "FYERS broker adapter ready"
        if not ready:
            message = "FYERS broker adapter missing credentials"

        self._logger.info(
            "broker_health_check",
            broker=self.adapter_name(),
            mode=mode,
            ready=ready,
            has_client_id=has_client_id,
            has_access_token=has_access_token,
        )

        return BrokerHealth(
            broker=self.adapter_name(),
            adapter="fyers",
            mode=mode,
            ready=ready,
            has_client_id=has_client_id,
            has_access_token=has_access_token,
            message=message,
        )

    def place_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        health = self.health_check()
        if not health.ready:
            return BrokerPlaceOrderResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="rejected",
                external_order_id=None,
                message="Broker credentials missing",
            )

        if self.is_live():
            self._logger.info(
                "fyers_live_place_order_skeleton_called",
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                order_type=request.order_type,
                product=request.product,
            )
            return BrokerPlaceOrderResponse(
                broker=self.adapter_name(),
                adapter="fyers",
                accepted=False,
                status="not_implemented",
                external_order_id=None,
                message="FYERS live order placement skeleton added; HTTP integration pending in Item 24",
            )

        synthetic_id = (
            f"stub-{request.symbol.replace(':', '_')}-"
            f"{request.side.lower()}-{request.quantity}"
        )
        self._logger.info(
            "fyers_stub_order_accepted",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            product=request.product,
            external_order_id=synthetic_id,
        )
        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id=synthetic_id,
            message="Stub broker accepted order",
        )
PY

cat > "$ROOT/services/execution_service/app/brokers/factory.py" <<'PY'
from __future__ import annotations

from services.execution_service.app.brokers.base import BrokerAdapter
from services.execution_service.app.brokers.fyers_adapter import FyersBrokerAdapter
from shared.config.settings import Settings


def build_broker_adapter(settings: Settings) -> BrokerAdapter:
    broker = settings.execution_service_broker.strip().lower()
    if broker in {"fyers_stub", "fyers_live"}:
        return FyersBrokerAdapter(settings=settings)
    raise ValueError(f"Unsupported execution broker: {settings.execution_service_broker}")
PY

cat > "$ROOT/services/execution_service/app/models.py" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class BrokerHealth(BaseModel):
    broker: str
    adapter: str
    mode: str
    ready: bool
    has_client_id: bool
    has_access_token: bool
    checked_at: datetime = Field(default_factory=utc_now)
    message: str


class BrokerPlaceOrderRequest(BaseModel):
    symbol: str
    side: str
    quantity: int
    order_type: str = "MARKET"
    product: str = "INTRADAY"
    validity: str = "DAY"
    strategy_name: str | None = None
    correlation_id: str | None = None


class BrokerPlaceOrderResponse(BaseModel):
    broker: str
    adapter: str
    accepted: bool
    status: str
    external_order_id: str | None = None
    processed_at: datetime = Field(default_factory=utc_now)
    message: str


class ExecutionServiceStatus(BaseModel):
    service: str
    mode: str
    broker: str
    broker_adapter: str
    broker_mode: str
    broker_ready: bool
    replay_ready: bool
    approved_loaded: int
    orders_prepared: int
    last_prepared_at: datetime | None = None
    message: str
PY

cat > "$ROOT/services/execution_service/app/processor.py" <<'PY'
from __future__ import annotations

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

    def build_broker_request(self, prepared_order: dict[str, str]) -> BrokerPlaceOrderRequest:
        request = BrokerPlaceOrderRequest(
            symbol=prepared_order["symbol"],
            side=prepared_order["side"],
            quantity=int(prepared_order["quantity"]),
            strategy_name="strategy_runtime_stub",
        )
        self._logger.info(
            "broker_order_request_built",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
        )
        return request
PY

cat > "$ROOT/services/execution_service/app/service.py" <<'PY'
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
PY

cat > "$ROOT/services/execution_service/app/api.py" <<'PY'
from fastapi import FastAPI

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.postgres.client import PostgresClient

app = FastAPI(title="execution_service", version="0.1.0")


def build_execution_service() -> ExecutionService:
    settings = get_settings()
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()
    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()
    service = ExecutionService(
        settings=settings,
        signal_reader=ApprovedSignalReader(
            signal_reader=StrategySignalReader(
                replay_reader=IndicatorReplayReader(repository=repository),
                strategy_processor=StrategyProcessor(),
            ),
            risk_processor=RiskProcessor(settings=settings),
        ),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
    )
    return service


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    status = build_execution_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "broker": status.broker,
        "broker_adapter": status.broker_adapter,
        "broker_mode": status.broker_mode,
        "broker_ready": status.broker_ready,
        "replay_ready": status.replay_ready,
        "approved_loaded": status.approved_loaded,
        "orders_prepared": status.orders_prepared,
        "last_prepared_at": status.last_prepared_at.isoformat() if status.last_prepared_at else None,
        "message": status.message,
        "status": "ok" if status.replay_ready else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, str | bool | int | None]:
    status = build_execution_service().get_status()
    return {
        "service": status.service,
        "mode": status.mode,
        "broker": status.broker,
        "broker_adapter": status.broker_adapter,
        "broker_mode": status.broker_mode,
        "broker_ready": status.broker_ready,
        "replay_ready": status.replay_ready,
        "approved_loaded": status.approved_loaded,
        "orders_prepared": status.orders_prepared,
        "last_prepared_at": status.last_prepared_at.isoformat() if status.last_prepared_at else None,
        "message": status.message,
    }


@app.get("/execution-service/broker/health")
def broker_health() -> dict[str, str | bool | None]:
    health = build_execution_service().get_broker_health()
    return {
        "broker": health.broker,
        "adapter": health.adapter,
        "mode": health.mode,
        "ready": health.ready,
        "has_client_id": health.has_client_id,
        "has_access_token": health.has_access_token,
        "checked_at": health.checked_at.isoformat(),
        "message": health.message,
    }


@app.post("/execution-service/prepare-once")
def prepare_once() -> dict[str, object]:
    service = build_execution_service()
    orders = service.prepare_once()
    return {
        "service": "execution_service",
        "order_count": len(orders),
        "orders": orders,
        "message": "Execution preparation completed",
    }


@app.post("/execution-service/broker/place-first")
def place_first() -> dict[str, object]:
    result = build_execution_service().place_first_prepared_order_once()
    return {
        "broker": result.broker,
        "adapter": result.adapter,
        "accepted": result.accepted,
        "status": result.status,
        "external_order_id": result.external_order_id,
        "processed_at": result.processed_at.isoformat(),
        "message": result.message,
    }
PY

cat > "$ROOT/services/execution_service/app/main.py" <<'PY'
import asyncio
import os

import uvicorn

from services.execution_service.app.api import app
from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from services.execution_service.app.signal_reader import ApprovedSignalReader
from services.indicator_engine.app.repository import IndicatorRepository
from services.risk_service.app.processor import RiskProcessor
from services.risk_service.app.signal_reader import StrategySignalReader
from services.strategy_runtime.app.processor import StrategyProcessor
from services.strategy_runtime.app.replay_reader import IndicatorReplayReader
from shared.config.settings import get_settings
from shared.logging.logger import configure_logging, get_logger
from shared.postgres.client import PostgresClient


async def run_stub_mode() -> None:
    settings = get_settings()
    logger = get_logger("execution_service")
    postgres_client = PostgresClient(settings=settings)
    postgres_client.connect()
    repository = IndicatorRepository(postgres_client=postgres_client)
    repository.ensure_table()

    broker_adapter = build_broker_adapter(settings=settings)

    service = ExecutionService(
        settings=settings,
        signal_reader=ApprovedSignalReader(
            signal_reader=StrategySignalReader(
                replay_reader=IndicatorReplayReader(repository=repository),
                strategy_processor=StrategyProcessor(),
            ),
            risk_processor=RiskProcessor(settings=settings),
        ),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=broker_adapter,
    )

    broker_health = broker_adapter.health_check()

    logger.info(
        "service_started",
        service="execution_service",
        env=settings.app_env,
        mode=settings.execution_service_mode,
        broker=settings.execution_service_broker,
        broker_ready=broker_health.ready,
        postgres_enabled=settings.postgres_enabled,
    )

    orders = service.prepare_once()
    postgres_client.close()

    logger.info(
        "execution_prepare_complete",
        service="execution_service",
        order_count=len(orders),
    )


def run_api_mode() -> None:
    settings = get_settings()
    logger = get_logger("execution_service")
    logger.info(
        "execution_service_api_starting",
        service="execution_service",
        env=settings.app_env,
        host=settings.execution_service_api_host,
        port=settings.execution_service_api_port,
        broker=settings.execution_service_broker,
        postgres_enabled=settings.postgres_enabled,
    )
    uvicorn.run(
        app,
        host=settings.execution_service_api_host,
        port=settings.execution_service_api_port,
        log_level=settings.log_level.lower(),
    )


def main() -> None:
    configure_logging()
    mode = os.getenv("EXECUTION_SERVICE_MODE", "stub").strip().lower()
    if mode == "api":
        run_api_mode()
        return
    asyncio.run(run_stub_mode())


if __name__ == "__main__":
    main()
PY

cat > "$ROOT/tests/unit/test_execution_service.py" <<'PY'
from datetime import UTC, datetime

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.processor import ExecutionProcessor
from services.execution_service.app.service import ExecutionService
from shared.config.settings import Settings


def build_settings(execution_broker: str = "fyers_stub") -> Settings:
    return Settings(
        APP_ENV="local",
        APP_NAME="projectX",
        LOG_LEVEL="INFO",
        POSTGRES_HOST="localhost",
        POSTGRES_PORT=5432,
        POSTGRES_DB="projectx",
        POSTGRES_USER="projectx",
        POSTGRES_PASSWORD="changeme",
        POSTGRES_ENABLED=False,
        REDIS_HOST="localhost",
        REDIS_PORT=6379,
        REDIS_ENABLED=False,
        REDIS_KEY_PREFIX="projectx",
        KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
        KAFKA_TOPIC_TICKS="md.raw.tick",
        KAFKA_TOPIC_BARS_1M="md.bar.1m",
        KAFKA_TOPIC_BARS_1M_CLOSED="md.bar.1m.closed",
        KAFKA_TOPIC_INDICATORS_1M="md.indicator.1m",
        KAFKA_CLIENT_ID="projectx-mdg",
        KAFKA_ENABLED=False,
        KAFKA_AUTO_CREATE_TOPICS=False,
        KAFKA_TOPIC_PARTITIONS=1,
        KAFKA_TOPIC_REPLICATION_FACTOR=1,
        KAFKA_CONSUMER_GROUP_BAR_BUILDER="projectx-bar-builder",
        KAFKA_CONSUMER_GROUP_INDICATOR_ENGINE="projectx-indicator-engine",
        KAFKA_CONSUMER_AUTO_OFFSET_RESET="earliest",
        FYERS_CLIENT_ID="client_id",
        FYERS_SECRET_KEY="secret_key",
        FYERS_REDIRECT_URI="http://localhost/callback",
        FYERS_ACCESS_TOKEN="token",
        AUTH_SESSION_FILE="data/auth/session.json",
        AUTH_REQUEST_TIMEOUT_SECONDS=10,
        AUTH_VALIDATE_ON_STARTUP=False,
        AUTH_SERVICE_MODE="bootstrap",
        MDG_MODE="stub",
        MDG_SYMBOLS="NSE:SBIN-EQ,NSE:RELIANCE-EQ",
        MDG_EXCHANGE="NSE",
        MDG_EMIT_INTERVAL_SECONDS=1,
        MDG_API_HOST="127.0.0.1",
        MDG_API_PORT=8002,
        BAR_BUILDER_MODE="stub",
        BAR_BUILDER_API_HOST="127.0.0.1",
        BAR_BUILDER_API_PORT=8003,
        BAR_BUILDER_TIMEFRAME="1m",
        BAR_BUILDER_CLOSE_ON_NEXT_MINUTE=True,
        INDICATOR_ENGINE_MODE="stub",
        INDICATOR_ENGINE_API_HOST="127.0.0.1",
        INDICATOR_ENGINE_API_PORT=8004,
        INDICATOR_ENGINE_TIMEFRAME="1m",
        STRATEGY_RUNTIME_MODE="stub",
        STRATEGY_RUNTIME_API_HOST="127.0.0.1",
        STRATEGY_RUNTIME_API_PORT=8005,
        STRATEGY_RUNTIME_NAME="ema_sma_cross_stub",
        RISK_SERVICE_MODE="stub",
        RISK_SERVICE_API_HOST="127.0.0.1",
        RISK_SERVICE_API_PORT=8006,
        RISK_MAX_OPEN_POSITIONS=5,
        RISK_MAX_SIGNAL_SIZE=1,
        EXECUTION_SERVICE_MODE="stub",
        EXECUTION_SERVICE_API_HOST="127.0.0.1",
        EXECUTION_SERVICE_API_PORT=8007,
        EXECUTION_SERVICE_BROKER=execution_broker,
    )


class FakeApprovedSignalReader:
    def load_approved_signals(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": "NSE:SBIN-EQ",
                "timeframe": "1m",
                "bar_start_time": datetime(2026, 3, 17, 17, 0, tzinfo=UTC).isoformat(),
                "signal": "BUY",
                "size": "1",
            }
        ]


def test_execution_processor_prepares_order() -> None:
    processor = ExecutionProcessor(settings=build_settings())
    orders = processor.prepare_orders(FakeApprovedSignalReader().load_approved_signals())
    assert len(orders) == 1
    assert orders[0]["side"] == "BUY"
    assert orders[0]["broker"] == "fyers_stub"
    assert orders[0]["status"] == "prepared"


def test_execution_service_prepares_once() -> None:
    settings = build_settings()
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
    )
    orders = service.prepare_once()
    status = service.get_status()
    assert len(orders) == 1
    assert status.service == "execution_service"
    assert status.approved_loaded == 1
    assert status.orders_prepared == 1
    assert status.broker == "fyers_stub"
    assert status.broker_adapter == "fyers"
    assert status.broker_ready is True


def test_execution_service_stub_broker_accepts_first_order() -> None:
    settings = build_settings("fyers_stub")
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
    )
    result = service.place_first_prepared_order_once()
    assert result.accepted is True
    assert result.status == "accepted"
    assert result.external_order_id is not None


def test_execution_service_live_broker_returns_not_implemented() -> None:
    settings = build_settings("fyers_live")
    service = ExecutionService(
        settings=settings,
        signal_reader=FakeApprovedSignalReader(),
        processor=ExecutionProcessor(settings=settings),
        broker_adapter=build_broker_adapter(settings=settings),
    )
    result = service.place_first_prepared_order_once()
    assert result.accepted is False
    assert result.status == "not_implemented"
PY

cat > "$ROOT/tests/unit/test_execution_service_api.py" <<'PY'
from fastapi.testclient import TestClient

from services.execution_service.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "execution_service"
    assert body["status"] == "ok"
    assert body["broker_adapter"] == "fyers"


def test_execution_status_endpoint() -> None:
    response = client.get("/execution-service/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "execution_service"
    assert body["broker"] == "fyers_stub"
    assert body["broker_adapter"] == "fyers"


def test_broker_health_endpoint() -> None:
    response = client.get("/execution-service/broker/health")
    assert response.status_code == 200
    body = response.json()
    assert body["broker"] == "fyers_stub"
    assert body["adapter"] == "fyers"
    assert body["ready"] is True


def test_prepare_once_endpoint() -> None:
    response = client.post("/execution-service/prepare-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "execution_service"
    assert "order_count" in body
    assert "orders" in body


def test_place_first_endpoint() -> None:
    response = client.post("/execution-service/broker/place-first")
    assert response.status_code == 200
    body = response.json()
    assert body["broker"] == "fyers_stub"
    assert body["adapter"] == "fyers"
    assert body["status"] in {"accepted", "not_implemented", "rejected", "empty"}
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()

marker = "# Item 23 — Broker adapter skeleton for FYERS"
if marker not in text:
    addition = """

# Item 23 — Broker adapter skeleton for FYERS
## Checklist

  * Add broker adapter interface
  * Add FYERS broker adapter skeleton
  * Add broker factory
  * Add broker health model
  * Add place-order request/response models
  * Add broker health endpoint
  * Add stub and live broker modes
  * Add execution service broker wiring
  * Add broker adapter unit tests
  * Add broker API tests
  * Verify tests pass
  * Verify stub broker accepts test order
  * Verify live broker returns skeleton response
  * Docs updated

## Definition of done

  * Code written
  * Config reused
  * Logs added
  * Test added
  * Local run successful
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 23 patch applied"
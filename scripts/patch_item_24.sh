#!/usr/bin/env bash
set -euo pipefail

ROOT="${1:-.}"

mkdir -p "$ROOT/services/execution_service/app/brokers"
mkdir -p "$ROOT/tests/unit"

cat > "$ROOT/services/execution_service/app/models.py" <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


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
    limit_price: float = 0.0
    stop_price: float = 0.0
    disclosed_qty: int = 0
    offline_order: bool = False
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy_name: str | None = None
    correlation_id: str | None = None
    idempotency_key: str | None = None
    source_bar_time: str | None = None

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return normalized

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be positive")
        return value

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"MARKET", "LIMIT", "STOP", "STOP_LIMIT"}
        if normalized not in allowed:
            raise ValueError(f"order_type must be one of {sorted(allowed)}")
        return normalized

    @field_validator("product")
    @classmethod
    def validate_product(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"INTRADAY", "CNC", "MARGIN", "CO", "BO"}
        if normalized not in allowed:
            raise ValueError(f"product must be one of {sorted(allowed)}")
        return normalized

    @field_validator("validity")
    @classmethod
    def validate_validity(cls, value: str) -> str:
        normalized = value.strip().upper()
        allowed = {"DAY", "IOC"}
        if normalized not in allowed:
            raise ValueError(f"validity must be one of {sorted(allowed)}")
        return normalized


class BrokerPlaceOrderResponse(BaseModel):
    broker: str
    adapter: str
    accepted: bool
    status: str
    external_order_id: str | None = None
    processed_at: datetime = Field(default_factory=utc_now)
    message: str
    correlation_id: str | None = None
    idempotency_key: str | None = None
    raw_response: dict[str, Any] | None = None


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
PY

cat > "$ROOT/services/execution_service/app/brokers/fyers_adapter.py" <<'PY'
from __future__ import annotations

from typing import Any

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
        message = "FYERS broker adapter ready" if ready else "FYERS broker adapter missing credentials"

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

    def _map_side(self, side: str) -> int:
        return 1 if side.upper() == "BUY" else -1

    def _map_order_type(self, order_type: str) -> int:
        normalized = order_type.upper()
        mapping = {
            "LIMIT": 1,
            "MARKET": 2,
            "STOP": 3,
            "STOP_LIMIT": 4,
        }
        return mapping[normalized]

    def _build_payload(self, request: BrokerPlaceOrderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "symbol": request.symbol,
            "qty": request.quantity,
            "type": self._map_order_type(request.order_type),
            "side": self._map_side(request.side),
            "productType": request.product,
            "limitPrice": request.limit_price,
            "stopPrice": request.stop_price,
            "validity": request.validity,
            "disclosedQty": request.disclosed_qty,
            "offlineOrder": request.offline_order,
            "stopLoss": request.stop_loss,
            "takeProfit": request.take_profit,
            "orderTag": request.idempotency_key or request.correlation_id or "execution_service",
        }
        return payload

    def _extract_order_id(self, response: dict[str, Any]) -> str | None:
        candidates = [
            response.get("id"),
            response.get("order_id"),
            response.get("orderId"),
        ]
        data = response.get("data")
        if isinstance(data, dict):
            candidates.extend(
                [
                    data.get("id"),
                    data.get("order_id"),
                    data.get("orderId"),
                ]
            )
        for candidate in candidates:
            if candidate:
                return str(candidate)
        return None

    def _is_success_response(self, response: dict[str, Any]) -> bool:
        if response.get("s") == "ok":
            return True
        if response.get("code") in {200, 201, 1101}:
            return True
        return False

    def _get_live_client(self) -> Any:
        try:
            from fyers_apiv3 import fyersModel
        except Exception as exc:
            raise RuntimeError("fyers_apiv3 package is not installed") from exc

        token = f"{self._settings.fyers_client_id}:{self._settings.fyers_access_token}"
        return fyersModel.FyersModel(
            client_id=self._settings.fyers_client_id,
            is_async=False,
            token=token,
            log_path="",
        )

    def _place_live_order(self, request: BrokerPlaceOrderRequest) -> BrokerPlaceOrderResponse:
        payload = self._build_payload(request)
        client = self._get_live_client()
        self._logger.info(
            "fyers_live_order_submit_started",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )
        raw_response = client.place_order(payload)
        if not isinstance(raw_response, dict):
            raw_response = {"raw": str(raw_response)}

        accepted = self._is_success_response(raw_response)
        external_order_id = self._extract_order_id(raw_response)
        status = "accepted" if accepted else "rejected"

        self._logger.info(
            "fyers_live_order_submit_finished",
            accepted=accepted,
            status=status,
            external_order_id=external_order_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )

        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=accepted,
            status=status,
            external_order_id=external_order_id,
            message=raw_response.get("message") or raw_response.get("msg") or "FYERS live order processed",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response=raw_response,
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
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
            )

        if self.is_live():
            try:
                return self._place_live_order(request)
            except Exception as exc:
                self._logger.exception(
                    "fyers_live_order_submit_failed",
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                )
                return BrokerPlaceOrderResponse(
                    broker=self.adapter_name(),
                    adapter="fyers",
                    accepted=False,
                    status="error",
                    external_order_id=None,
                    message=f"FYERS live order failed: {exc.__class__.__name__}: {exc}",
                    correlation_id=request.correlation_id,
                    idempotency_key=request.idempotency_key,
                )

        synthetic_id = (
            f"stub-{request.symbol.replace(':', '_')}-"
            f"{request.side.lower()}-{request.quantity}-"
            f"{request.idempotency_key or 'na'}"
        )
        self._logger.info(
            "fyers_stub_order_accepted",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            product=request.product,
            external_order_id=synthetic_id,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
        )
        return BrokerPlaceOrderResponse(
            broker=self.adapter_name(),
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id=synthetic_id,
            message="Stub broker accepted order",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response=self._build_payload(request),
        )
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
from services.execution_service.app.models import BrokerPlaceOrderResponse
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
    return ExecutionService(
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


@app.get("/health")
def health() -> dict[str, str | bool | int | None]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)
    broker_health = broker_adapter.health_check()

    replay_ready = True
    approved_loaded = 0
    message = "Execution service ready"

    try:
        service = build_execution_service()
        status = service.get_status()
        replay_ready = status.replay_ready
        approved_loaded = status.approved_loaded
    except Exception as exc:
        replay_ready = False
        message = f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})"

    return {
        "service": "execution_service",
        "mode": settings.execution_service_mode,
        "broker": settings.execution_service_broker,
        "broker_adapter": broker_health.adapter,
        "broker_mode": broker_health.mode,
        "broker_ready": broker_health.ready,
        "replay_ready": replay_ready,
        "approved_loaded": approved_loaded,
        "orders_prepared": 0,
        "last_prepared_at": None,
        "message": message,
        "status": "ok" if broker_health.ready else "degraded",
    }


@app.get("/execution-service/status")
def execution_status() -> dict[str, str | bool | int | None]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)
    broker_health = broker_adapter.health_check()

    try:
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
    except Exception as exc:
        return {
            "service": "execution_service",
            "mode": settings.execution_service_mode,
            "broker": settings.execution_service_broker,
            "broker_adapter": broker_health.adapter,
            "broker_mode": broker_health.mode,
            "broker_ready": broker_health.ready,
            "replay_ready": False,
            "approved_loaded": 0,
            "orders_prepared": 0,
            "last_prepared_at": None,
            "message": f"Execution service degraded: replay storage unavailable ({exc.__class__.__name__})",
        }


@app.get("/execution-service/broker/health")
def broker_health() -> dict[str, str | bool | None]:
    health = build_broker_adapter(settings=get_settings()).health_check()
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
    try:
        service = build_execution_service()
        orders = service.prepare_once()
        return {
            "service": "execution_service",
            "order_count": len(orders),
            "orders": orders,
            "message": "Execution preparation completed",
        }
    except Exception as exc:
        return {
            "service": "execution_service",
            "order_count": 0,
            "orders": [],
            "message": f"Execution preparation unavailable: replay storage unavailable ({exc.__class__.__name__})",
        }


@app.post("/execution-service/broker/place-first")
def place_first() -> dict[str, object]:
    settings = get_settings()
    broker_adapter = build_broker_adapter(settings=settings)

    try:
        result = build_execution_service().place_first_prepared_order_once()
    except Exception:
        result = BrokerPlaceOrderResponse(
            broker=settings.execution_service_broker,
            adapter=broker_adapter.health_check().adapter,
            accepted=False,
            status="unavailable",
            external_order_id=None,
            message="Broker placement unavailable because replay storage is not available",
        )

    return {
        "broker": result.broker,
        "adapter": result.adapter,
        "accepted": result.accepted,
        "status": result.status,
        "external_order_id": result.external_order_id,
        "processed_at": result.processed_at.isoformat(),
        "message": result.message,
        "correlation_id": result.correlation_id,
        "idempotency_key": result.idempotency_key,
        "raw_response": result.raw_response,
    }
PY

cat > "$ROOT/tests/unit/test_execution_service.py" <<'PY'
from datetime import UTC, datetime

from services.execution_service.app.brokers.factory import build_broker_adapter
from services.execution_service.app.models import BrokerPlaceOrderRequest
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


def test_execution_processor_builds_request_with_idempotency() -> None:
    processor = ExecutionProcessor(settings=build_settings())
    order = processor.prepare_orders(FakeApprovedSignalReader().load_approved_signals())[0]
    request = processor.build_broker_request(order)
    assert request.side == "BUY"
    assert request.quantity == 1
    assert request.idempotency_key is not None
    assert len(request.idempotency_key) == 24
    assert request.correlation_id is not None


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
    assert result.idempotency_key is not None


def test_execution_request_validates_side() -> None:
    try:
        BrokerPlaceOrderRequest(symbol="NSE:SBIN-EQ", side="HOLD", quantity=1)
    except Exception as exc:
        assert "side must be BUY or SELL" in str(exc)
    else:
        raise AssertionError("Expected invalid side validation error")


def test_execution_live_broker_error_when_sdk_missing_or_call_fails() -> None:
    settings = build_settings("fyers_live")
    adapter = build_broker_adapter(settings=settings)
    request = BrokerPlaceOrderRequest(
        symbol="NSE:SBIN-EQ",
        side="BUY",
        quantity=1,
        correlation_id="test-correlation",
        idempotency_key="test-idempotency",
    )
    result = adapter.place_order(request)
    assert result.accepted is False
    assert result.status in {"accepted", "rejected", "error"}
PY

cat > "$ROOT/tests/unit/test_execution_service_api.py" <<'PY'
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
from services.execution_service.app.models import (
    BrokerHealth,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
)
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def get_status(self) -> ExecutionServiceStatus:
        return ExecutionServiceStatus(
            service="execution_service",
            mode="stub",
            broker="fyers_stub",
            broker_adapter="fyers",
            broker_mode="stub",
            broker_ready=True,
            replay_ready=True,
            approved_loaded=1,
            orders_prepared=1,
            last_prepared_at=datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
            message="Execution service ready",
        )

    def get_broker_health(self) -> BrokerHealth:
        return BrokerHealth(
            broker="fyers_stub",
            adapter="fyers",
            mode="stub",
            ready=True,
            has_client_id=True,
            has_access_token=True,
            message="FYERS broker adapter ready",
        )

    def prepare_once(self) -> list[dict[str, str]]:
        return [
            {
                "symbol": "NSE:SBIN-EQ",
                "timeframe": "1m",
                "bar_start_time": datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(),
                "side": "BUY",
                "quantity": "1",
                "broker": "fyers_stub",
                "status": "prepared",
            }
        ]

    def place_first_prepared_order_once(self) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id="stub-NSE_SBIN-EQ-buy-1-test",
            message="Stub broker accepted order",
            correlation_id="NSE:SBIN-EQ|1m|2026-03-18T12:00:00+00:00",
            idempotency_key="aaaaaaaaaaaaaaaaaaaaaaaa",
            raw_response={"symbol": "NSE:SBIN-EQ"},
        )


execution_api.build_execution_service = lambda: FakeExecutionService()

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
    assert body["order_count"] == 1
    assert len(body["orders"]) == 1


def test_place_first_endpoint() -> None:
    response = client.post("/execution-service/broker/place-first")
    assert response.status_code == 200
    body = response.json()
    assert body["broker"] == "fyers_stub"
    assert body["adapter"] == "fyers"
    assert body["status"] == "accepted"
    assert body["idempotency_key"] == "aaaaaaaaaaaaaaaaaaaaaaaa"
PY

python3 - <<'PY' "$ROOT/Architecture.md"
from pathlib import Path
import sys

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

text = path.read_text()
marker = "# Item 24 — Order command to broker order placement"
if marker not in text:
    addition = """

# Item 24 — Order command to broker order placement
## Checklist

  * Add broker request validation
  * Add idempotency key generation
  * Add correlation id on order submission
  * Add FYERS payload mapping
  * Add stub broker submission payload echo
  * Add live FYERS place-order call
  * Add response normalization
  * Add live submission error handling
  * Add processor tests for idempotency
  * Add broker request validation tests
  * Add API test coverage for broker response fields
  * Verify tests pass
  * Verify stub path returns accepted with idempotency key
  * Verify live path returns accepted or controlled error
  * Docs updated

## Definition of done

  * Code written
  * Request validation added
  * Idempotency added
  * Logs added
  * Test added
  * Stub mode verified
  * Live mode path implemented
  * Failure case checked
  * Output verified
  * Docs updated
"""
    text = text.rstrip() + addition + "\n"
    path.write_text(text)
PY

echo "[OK] Item 24 patch applied"
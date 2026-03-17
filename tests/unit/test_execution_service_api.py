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
            active_order_count=1,
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
            order_id="ord-prepared-api",
        )

    def submit_order_request(self, request, submit_message: str) -> BrokerPlaceOrderResponse:
        if request.idempotency_key == "manual-test-idempotency":
            return BrokerPlaceOrderResponse(
                broker="fyers_stub",
                adapter="fyers",
                accepted=True,
                status="accepted",
                external_order_id="stub-NSE_SBIN-EQ-buy-1-test",
                message=submit_message,
                correlation_id=request.correlation_id,
                idempotency_key=request.idempotency_key,
                raw_response={"symbol": "NSE:SBIN-EQ"},
                order_id="ord-manual-test-api",
            )
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="duplicate",
            external_order_id=None,
            message="duplicate",
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response={"duplicate": True},
            order_id="ord-manual-test-api",
            duplicate_of_order_id="ord-manual-test-api",
        )

    def list_order_lifecycle(self):
        return []

    def get_order_history(self, order_id: str):
        return []


execution_api.build_execution_service = lambda: FakeExecutionService()
execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

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
    assert body["order_id"] == "ord-prepared-api"


def test_place_test_endpoint() -> None:
    response = client.post("/execution-service/broker/place-test")
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["idempotency_key"] == "manual-test-idempotency"
    assert body["order_id"] == "ord-manual-test-api"


def test_order_listing_endpoint() -> None:
    response = client.get("/execution-service/orders")
    assert response.status_code == 200
    body = response.json()
    assert "orders" in body


def test_order_history_endpoint_404_when_missing() -> None:
    response = client.get("/execution-service/orders/ord-unknown/history")
    assert response.status_code == 404

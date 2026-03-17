from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
from services.execution_service.app.models import (
    BrokerHealth,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
)
from services.execution_service.app.order_state_machine import OrderStatus
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


def test_place_test_endpoint() -> None:
    response = client.post("/execution-service/broker/place-test")
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is True
    assert body["idempotency_key"] == "manual-test-idempotency"


def test_order_listing_and_history_endpoints() -> None:
    create_response = client.post("/execution-service/broker/place-test")
    assert create_response.status_code == 200

    orders_response = client.get("/execution-service/orders")
    assert orders_response.status_code == 200
    orders_body = orders_response.json()
    assert "orders" in orders_body

    if orders_body["count"] > 0:
        order_id = orders_body["orders"][0]["order_id"]
        update_response = client.post(
            f"/execution-service/orders/{order_id}/broker-update",
            json={"broker_status": "OPEN"},
        )
        assert update_response.status_code in {200, 404, 400}

        history_response = client.get(f"/execution-service/orders/{order_id}/history")
        assert history_response.status_code == 200

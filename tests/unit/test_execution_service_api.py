from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
from services.execution_service.app.models import (
    BrokerActionResponse,
    BrokerHealth,
    BrokerPlaceOrderResponse,
    ExecutionServiceStatus,
    OrderEventView,
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

    def prepare_once(self) -> list[dict[str, str]]:
        return [{"symbol": "NSE:SBIN-EQ", "timeframe": "1m", "bar_start_time": datetime(2026, 3, 18, 12, 0, tzinfo=UTC).isoformat(), "side": "BUY", "quantity": "1", "broker": "fyers_stub", "status": "prepared"}]

    def place_first_prepared_order_once(self) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id="stub-order",
            message="Stub broker accepted order",
            correlation_id="corr",
            idempotency_key="idem",
            raw_response={"symbol": "NSE:SBIN-EQ"},
            order_id="ord-prepared-api",
        )

    def submit_order_request(self, request, submit_message: str) -> BrokerPlaceOrderResponse:
        return BrokerPlaceOrderResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="accepted",
            external_order_id="stub-order",
            message=submit_message,
            correlation_id=request.correlation_id,
            idempotency_key=request.idempotency_key,
            raw_response={"symbol": "NSE:SBIN-EQ"},
            order_id="ord-manual-test-api",
        )

    def list_order_lifecycle(self):
        return []

    def get_order_history(self, order_id: str):
        return []

    def consume_broker_update(self, payload: dict[str, object], source: str = "api") -> OrderEventView:
        return OrderEventView(
            order_id="ord-manual-test-api",
            from_status=OrderStatus.ACKNOWLEDGED,
            to_status=OrderStatus.OPEN,
            event_type="broker_update",
            event_time=datetime(2026, 3, 18, 12, 1, tzinfo=UTC),
            message="Broker update mapped from OPEN",
            raw_payload={"external_order_id": "ext-1", "update_source": source},
        )

    def cancel_order(self, order_id: str) -> BrokerActionResponse:
        return BrokerActionResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="cancelled",
            external_order_id="stub-order",
            message="Stub broker cancelled order",
            correlation_id="corr",
            idempotency_key="idem",
            raw_response={"operation": "cancel"},
            order_id=order_id,
        )

    def modify_order(self, order_id: str, **kwargs) -> BrokerActionResponse:
        return BrokerActionResponse(
            broker="fyers_stub",
            adapter="fyers",
            accepted=True,
            status="modified",
            external_order_id="stub-order",
            message="Stub broker modified order",
            correlation_id="corr",
            idempotency_key="idem",
            raw_response={"operation": "modify", **kwargs},
            order_id=order_id,
        )


execution_api.build_execution_service = lambda: FakeExecutionService()
execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_place_test_endpoint() -> None:
    response = client.post("/execution-service/broker/place-test")
    assert response.status_code == 200
    assert response.json()["order_id"] == "ord-manual-test-api"


def test_consume_broker_update_endpoint() -> None:
    response = client.post(
        "/execution-service/broker/consume-update",
        json={"external_order_id": "ext-1", "status": "OPEN"},
    )
    assert response.status_code == 200
    assert response.json()["event"]["to_status"] == "open"


def test_cancel_endpoint() -> None:
    response = client.post("/execution-service/orders/ord-1/cancel")
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == "ord-1"
    assert body["status"] == "cancelled"


def test_modify_endpoint() -> None:
    response = client.post(
        "/execution-service/orders/ord-1/modify",
        json={"quantity": 2, "limit_price": 601.5},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["order_id"] == "ord-1"
    assert body["status"] == "modified"
    assert body["raw_response"]["quantity"] == 2

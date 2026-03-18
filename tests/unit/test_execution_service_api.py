from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    @property
    def execution_risk_limits(self):
        return {
            "max_order_quantity": 1,
            "max_symbol_position_quantity": 1,
            "max_open_positions": 5,
        }

    def evaluate_execution_risk(self, request):
        class Decision:
            allowed = request.quantity <= 1
            reason = "Execution risk checks passed" if request.quantity <= 1 else "Order quantity 2 exceeds max_order_quantity 1"
            code = "allowed" if request.quantity <= 1 else "max_order_quantity_exceeded"
        return Decision()


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_execution_risk_check_endpoint_allowed() -> None:
    response = client.post(
        "/execution-service/risk/check",
        json={"symbol": "NSE:SBIN-EQ", "side": "BUY", "quantity": 1},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk"]["allowed"] is True
    assert body["risk"]["code"] == "allowed"


def test_execution_risk_check_endpoint_rejected() -> None:
    response = client.post(
        "/execution-service/risk/check",
        json={"symbol": "NSE:SBIN-EQ", "side": "BUY", "quantity": 2},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["risk"]["allowed"] is False
    assert body["risk"]["code"] == "max_order_quantity_exceeded"

from fastapi.testclient import TestClient

from services.risk_service.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "risk_service"
    assert body["status"] == "ok"


def test_risk_status_endpoint() -> None:
    response = client.get("/risk-service/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "risk_service"
    assert body["source"] == "strategy_runtime_replay"


def test_evaluate_once_endpoint() -> None:
    response = client.post("/risk-service/evaluate-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "risk_service"
    assert "approved_count" in body
    assert "rejected_count" in body
from fastapi.testclient import TestClient

from services.strategy_runtime.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "strategy_runtime"
    assert body["status"] == "ok"


def test_strategy_status_endpoint() -> None:
    response = client.get("/strategy-runtime/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "strategy_runtime"
    assert body["strategy_name"] == "ema_sma_cross_stub"
    assert body["source_table"] == "indicators_1m"


def test_evaluate_once_endpoint() -> None:
    response = client.post("/strategy-runtime/evaluate-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "strategy_runtime"
    assert "signal_count" in body
    assert "signals" in body
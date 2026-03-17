from fastapi.testclient import TestClient

from services.market_data_gateway.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "market_data_gateway"
    assert body["connected"] is True
    assert body["status"] == "ok"


def test_gateway_status_endpoint() -> None:
    response = client.get("/gateway/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "market_data_gateway"
    assert body["connected"] is True
    assert body["mode"] in {"stub", "api"}


def test_emit_once_endpoint() -> None:
    response = client.post("/gateway/emit-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "market_data_gateway"
    assert body["emitted_count"] == 2
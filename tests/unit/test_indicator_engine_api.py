from fastapi.testclient import TestClient

from services.indicator_engine.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "indicator_engine"
    assert body["connected"] is True
    assert body["status"] == "ok"


def test_indicator_status_endpoint() -> None:
    response = client.get("/indicator-engine/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "indicator_engine"
    assert body["connected"] is True
    assert body["source_topic"] == "md.bar.1m.closed"
    assert body["target_topic"] == "md.indicator.1m"


def test_indicator_consume_once_endpoint() -> None:
    response = client.post("/indicator-engine/consume-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "indicator_engine"
    assert "produced_count" in body
from fastapi.testclient import TestClient

from services.indicator_engine.app.api import app

client = TestClient(app)


def test_replay_status_endpoint() -> None:
    response = client.get("/indicator-engine/replay/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "indicator_engine"
    assert body["replay_ready"] is True
    assert body["source_table"] == "indicators_1m"
    assert "records_loaded" in body


def test_replay_indicators_endpoint() -> None:
    response = client.get("/indicator-engine/replay/indicators")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "indicator_engine"
    assert "record_count" in body
    assert "records" in body
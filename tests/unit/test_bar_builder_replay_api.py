from fastapi.testclient import TestClient

from services.bar_builder.app.api import app

client = TestClient(app)


def test_replay_status_endpoint() -> None:
    response = client.get("/bar-builder/replay/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bar_builder"
    assert body["replay_ready"] is True
    assert body["source_table"] == "closed_bars_1m"
    assert "records_loaded" in body


def test_replay_closed_bars_endpoint() -> None:
    response = client.get("/bar-builder/replay/closed-bars")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bar_builder"
    assert "record_count" in body
    assert "records" in body
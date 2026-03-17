from fastapi.testclient import TestClient

from services.bar_builder.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bar_builder"
    assert body["connected"] is True
    assert body["status"] == "ok"
    assert "open_bar_count" in body
    assert "closed_count" in body
    assert "closed_topic" in body


def test_bar_builder_status_endpoint() -> None:
    response = client.get("/bar-builder/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bar_builder"
    assert body["connected"] is True
    assert body["source_topic"] == "md.raw.tick"
    assert body["target_topic"] == "md.bar.1m"
    assert body["closed_topic"] == "md.bar.1m.closed"
    assert "open_bar_count" in body
    assert "closed_count" in body


def test_bar_builder_consume_once_endpoint() -> None:
    response = client.post("/bar-builder/consume-once")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "bar_builder"
    assert "built_count" in body
    assert "closed_count" in body
    assert "open_bar_count" in body
from fastapi.testclient import TestClient

from services.auth_service.app.api import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "auth_service"
    assert "status" in body
    assert "authenticated" in body
    assert "session_present" in body
    assert "token_expired" in body
    assert "message" in body


def test_auth_status_endpoint() -> None:
    response = client.get("/auth/status")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "auth_service"
    assert "authenticated" in body
    assert "session_present" in body
    assert "token_expired" in body
    assert "message" in body


def test_auth_bootstrap_endpoint() -> None:
    response = client.post("/auth/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "auth_service"
    assert body["session_present"] is True
    assert "authenticated" in body
    assert "token_type" in body
    assert "message" in body
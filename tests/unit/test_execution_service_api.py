from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def add_operator_note(self, request):
        class E:
            audit_id = "audit-123"
            event_type = "operator_note"
            message = request.message
            event_time = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
            order_id = request.order_id
            symbol = request.symbol
            actor = request.actor
            metadata = request.metadata
        return E()

    def list_audit_events(self, order_id=None, limit=None):
        class E:
            pass
        e = E()
        e.audit_id = "audit-123"
        e.event_type = "operator_note"
        e.message = "Manual note"
        e.event_time = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        e.order_id = order_id
        e.symbol = "NSE:SBIN-EQ"
        e.actor = "operator"
        e.metadata = {"tag": "manual"}
        return [e]


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_add_audit_note_endpoint() -> None:
    response = client.post(
        "/execution-service/audit/note",
        json={"message": "Manual note", "symbol": "NSE:SBIN-EQ", "actor": "operator"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_type"] == "operator_note"
    assert body["event"]["message"] == "Manual note"


def test_list_audit_events_endpoint() -> None:
    response = client.get("/execution-service/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["events"][0]["event_type"] == "operator_note"

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def list_trades(self, symbol=None):
        class T:
            pass
        t = T()
        t.trade_id = "trd-NSE_SBIN-EQ-000001"
        t.symbol = "NSE:SBIN-EQ"
        t.entry_side = "BUY"
        t.entry_quantity = 1
        t.entry_price = 600.0
        t.entry_time = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        t.exit_quantity = 1
        t.exit_price = 610.0
        t.exit_time = datetime(2026, 3, 18, 12, 5, tzinfo=UTC)
        t.realized_pnl = 10.0
        t.status = "CLOSED"
        t.entry_order_id = "ord-1"
        t.exit_order_id = "ord-2"
        t.metadata = {"source": "test"}
        if symbol is None or symbol == "NSE:SBIN-EQ":
            return [t]
        return []


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_list_trades_endpoint() -> None:
    response = client.get("/execution-service/trades")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["trades"][0]["trade_id"] == "trd-NSE_SBIN-EQ-000001"


def test_list_trades_by_symbol_endpoint() -> None:
    response = client.get("/execution-service/trades/NSE:SBIN-EQ")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "NSE:SBIN-EQ"
    assert body["count"] == 1
    assert body["trades"][0]["realized_pnl"] == 10.0

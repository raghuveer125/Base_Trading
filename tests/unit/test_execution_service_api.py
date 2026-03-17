from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def __init__(self) -> None:
        self._position = {
            "symbol": "NSE:SBIN-EQ",
            "net_quantity": 1,
            "avg_price": 600.25,
            "side": "LONG",
            "realized_pnl": 0.0,
            "open_lots": [{"quantity": 1, "price": 600.25, "side": "BUY"}],
            "updated_at": datetime(2026, 3, 18, 12, 0, tzinfo=UTC),
        }

    def list_positions(self):
        class P:
            pass
        p = P()
        p.symbol = self._position["symbol"]
        p.net_quantity = self._position["net_quantity"]
        p.avg_price = self._position["avg_price"]
        p.side = self._position["side"]
        p.realized_pnl = self._position["realized_pnl"]
        p.open_lots = [type("Lot", (), lot)() for lot in self._position["open_lots"]]
        p.updated_at = self._position["updated_at"]
        return [p]

    def get_position(self, symbol: str):
        class P:
            pass
        p = P()
        p.symbol = self._position["symbol"]
        p.net_quantity = self._position["net_quantity"]
        p.avg_price = self._position["avg_price"]
        p.side = self._position["side"]
        p.realized_pnl = self._position["realized_pnl"]
        p.open_lots = [type("Lot", (), lot)() for lot in self._position["open_lots"]]
        p.updated_at = self._position["updated_at"]
        return p


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_positions_endpoint() -> None:
    response = client.get("/execution-service/positions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["positions"][0]["symbol"] == "NSE:SBIN-EQ"
    assert body["positions"][0]["net_quantity"] == 1


def test_single_position_endpoint() -> None:
    response = client.get("/execution-service/positions/NSE:SBIN-EQ")
    assert response.status_code == 200
    body = response.json()
    assert body["position"]["symbol"] == "NSE:SBIN-EQ"
    assert body["position"]["side"] == "LONG"

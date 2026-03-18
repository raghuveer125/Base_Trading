from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def list_positions(self):
        class P:
            pass
        p = P()
        p.symbol = "NSE:SBIN-EQ"
        p.net_quantity = 1
        p.avg_price = 600.25
        p.side = "LONG"
        p.realized_pnl = 0.0
        p.open_lots = [type("Lot", (), {"quantity": 1, "price": 600.25, "side": "BUY"})()]
        p.updated_at = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        return [p]

    def get_position(self, symbol: str):
        class P:
            pass
        p = P()
        p.symbol = "NSE:SBIN-EQ"
        p.net_quantity = 1
        p.avg_price = 600.25
        p.side = "LONG"
        p.realized_pnl = 0.0
        p.open_lots = [type("Lot", (), {"quantity": 1, "price": 600.25, "side": "BUY"})()]
        p.updated_at = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        return p

    def get_portfolio(self):
        class P:
            pass
        p = P()
        p.open_position_count = 1
        p.gross_quantity = 1
        p.net_quantity = 1
        p.realized_pnl = 0.0
        p.long_position_count = 1
        p.short_position_count = 0
        p.symbols = ["NSE:SBIN-EQ"]
        p.updated_at = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        return p


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_positions_endpoint() -> None:
    response = client.get("/execution-service/positions")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["positions"][0]["symbol"] == "NSE:SBIN-EQ"


def test_single_position_endpoint() -> None:
    response = client.get("/execution-service/positions/NSE:SBIN-EQ")
    assert response.status_code == 200
    body = response.json()
    assert body["position"]["side"] == "LONG"


def test_portfolio_endpoint() -> None:
    response = client.get("/execution-service/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio"]["open_position_count"] == 1

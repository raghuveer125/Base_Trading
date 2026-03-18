from datetime import UTC, datetime

from fastapi.testclient import TestClient

from services.execution_service.app.api import app
import services.execution_service.app.api as execution_api


class FakeExecutionService:
    def __init__(self):
        self.marks = {}

    def set_mark_price(self, symbol: str, price: float) -> None:
        self.marks[symbol] = price

    def get_position_pnl(self, symbol: str):
        class P:
            pass
        p = P()
        p.symbol = symbol
        p.side = "LONG"
        p.net_quantity = 1
        p.avg_price = 600.0
        p.mark_price = self.marks.get(symbol, 615.0)
        p.unrealized_pnl = p.mark_price - 600.0
        p.realized_pnl = 0.0
        p.total_pnl = p.unrealized_pnl
        p.updated_at = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        return p

    def get_portfolio_pnl(self):
        class P:
            pass
        class Pos:
            pass
        pos = Pos()
        pos.symbol = "NSE:SBIN-EQ"
        pos.side = "LONG"
        pos.net_quantity = 1
        pos.avg_price = 600.0
        pos.mark_price = 615.0
        pos.unrealized_pnl = 15.0
        pos.realized_pnl = 0.0
        pos.total_pnl = 15.0
        pos.updated_at = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)

        p = P()
        p.realized_pnl = 0.0
        p.unrealized_pnl = 15.0
        p.total_pnl = 15.0
        p.updated_at = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)
        p.positions = [pos]
        return p


execution_api.build_lifecycle_only_service = lambda: FakeExecutionService()

client = TestClient(app)


def test_set_mark_price_endpoint() -> None:
    response = client.post("/execution-service/marks", json={"symbol": "NSE:SBIN-EQ", "price": 615.0})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mark_price"] == 615.0


def test_position_pnl_endpoint() -> None:
    response = client.get("/execution-service/pnl/positions/NSE:SBIN-EQ")
    assert response.status_code == 200
    body = response.json()
    assert body["position_pnl"]["symbol"] == "NSE:SBIN-EQ"
    assert body["position_pnl"]["unrealized_pnl"] == 15.0


def test_portfolio_pnl_endpoint() -> None:
    response = client.get("/execution-service/pnl/portfolio")
    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_pnl"]["total_pnl"] == 15.0
    assert len(body["portfolio_pnl"]["positions"]) == 1

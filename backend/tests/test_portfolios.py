"""
Tests for portfolio and holding endpoints.
"""

from .conftest import AUTH_HEADER


def test_create_portfolio(client):
    """POST /portfolios should create a portfolio."""
    r = client.post(
        "/portfolios",
        json={"name": "Long-term Stocks", "portfolio_type": "stocks"},
        headers=AUTH_HEADER,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Long-term Stocks"
    assert data["portfolio_type"] == "stocks"


def test_list_portfolios(client):
    """GET /portfolios should return user portfolios."""
    client.post(
        "/portfolios",
        json={"name": "Crypto", "portfolio_type": "crypto"},
        headers=AUTH_HEADER,
    )
    r = client.get("/portfolios", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_add_holding(client):
    """POST /portfolios/{id}/holdings should add a holding."""
    r = client.post(
        "/portfolios",
        json={"name": "MF Portfolio", "portfolio_type": "mutual_funds"},
        headers=AUTH_HEADER,
    )
    pid = r.json()["id"]

    r = client.post(
        f"/portfolios/{pid}/holdings",
        json={
            "symbol": "NIFTYBEES",
            "name": "Nippon India Nifty BeES",
            "quantity": "100",
            "buy_price": "250",
            "current_price": "270",
            "asset_type": "etf",
        },
        headers=AUTH_HEADER,
    )
    assert r.status_code == 201
    data = r.json()
    assert data["symbol"] == "NIFTYBEES"
    assert float(data["quantity"]) == 100


def test_list_holdings(client):
    """GET /portfolios/{id}/holdings should return holdings."""
    r = client.post(
        "/portfolios",
        json={"name": "Test", "portfolio_type": "stocks"},
        headers=AUTH_HEADER,
    )
    pid = r.json()["id"]

    client.post(
        f"/portfolios/{pid}/holdings",
        json={
            "symbol": "RELIANCE",
            "name": "Reliance Industries",
            "quantity": "10",
            "buy_price": "2500",
            "current_price": "2800",
            "asset_type": "equity",
        },
        headers=AUTH_HEADER,
    )

    r = client.get(f"/portfolios/{pid}/holdings", headers=AUTH_HEADER)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["symbol"] == "RELIANCE"


def test_delete_portfolio(client):
    """DELETE /portfolios/{id} should remove the portfolio."""
    r = client.post(
        "/portfolios",
        json={"name": "Temp", "portfolio_type": "gold"},
        headers=AUTH_HEADER,
    )
    pid = r.json()["id"]
    r = client.delete(f"/portfolios/{pid}", headers=AUTH_HEADER)
    assert r.status_code == 200

    r = client.get("/portfolios", headers=AUTH_HEADER)
    assert len(r.json()) == 0


def test_portfolio_summary(client):
    """GET /portfolios/summary should return aggregate data."""
    r = client.get("/portfolios/summary", headers=AUTH_HEADER)
    assert r.status_code == 200
    data = r.json()
    assert "total_invested" in data
    assert "total_pnl" in data

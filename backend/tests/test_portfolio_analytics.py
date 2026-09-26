from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.services.portfolio_analytics import compute_portfolio_analytics


def test_portfolio_analytics_labels_user_entered_and_stale_prices():
    portfolio = SimpleNamespace(id="portfolio-1")
    holdings = [
        SimpleNamespace(
            id="fresh", symbol="ABC", quantity=Decimal("1"), buy_price=Decimal("100"),
            current_price=Decimal("110"), asset_type="equity", purchase_date=date.today(),
            updated_at=datetime.now(UTC),
        ),
        SimpleNamespace(
            id="old", symbol="XYZ", quantity=Decimal("1"), buy_price=Decimal("100"),
            current_price=Decimal("90"), asset_type="equity", purchase_date=date.today(),
            updated_at=datetime.now(UTC) - timedelta(days=31),
        ),
    ]
    result = compute_portfolio_analytics([portfolio], {portfolio.id: holdings})
    assert result["valuation_quality"]["source"] == "user_entered"
    assert result["valuation_quality"]["live_prices_available"] is False
    assert result["valuation_quality"]["stale_holding_count"] == 1
    assert {item["status"] for item in result["valuation_quality"]["holdings"]} == {"stale", "user_entered_current"}

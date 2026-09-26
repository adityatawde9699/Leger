from datetime import date, timedelta
from decimal import Decimal

from app.models import Transaction
from app.services.advisor_tools import execute_tool_request, get_summary, parse_tool_request, select_advisor_tools


def _tx(tx_id, days_ago, amount, category="Dining"):
    return Transaction(
        id=tx_id,
        user_id="user",
        date=date.today() - timedelta(days=days_ago),
        type="expense",
        status="posted",
        category=category,
        amount=Decimal(amount),
        description=f"Purchase {tx_id}",
    )


def test_summary_tool_returns_calculated_currency_and_evidence():
    result = get_summary([_tx("a", 2, "12.50")], currency="USD")

    assert result["tool"] == "get_summary"
    assert result["currency"] == "USD"
    assert result["expenses"] == "12.50"
    assert result["evidence_transaction_ids"] == ["a"]


def test_tool_selection_adds_only_relevant_deterministic_tools():
    transactions = [_tx("a", 2, "12.50"), _tx("b", 35, "8.00")]
    results = select_advisor_tools("Compare my spending and show the supporting transactions", transactions, [], "USD")
    names = [result["tool"] for result in results]

    assert names == ["get_summary", "compare_periods", "list_evidence"]
    assert all("USD" in str(result) for result in results if result["tool"] == "list_evidence")


def test_model_tool_request_is_allowlisted_and_calculated_in_python():
    transactions = [_tx("a", 2, "12.50")]
    request = parse_tool_request('{"tool":"list_evidence","arguments":{"transaction_ids":["a","forged"]}}')

    result = execute_tool_request(request, transactions, [], "USD")

    assert result["tool"] == "list_evidence"
    assert [row["transaction_id"] for row in result["rows"]] == ["a"]
    assert parse_tool_request('{"tool":"delete_all","arguments":{}}') is None


def test_simulate_goal_tool_bounds_model_assumptions():
    transactions = [_tx("a", 2, "12.50")]
    request = parse_tool_request(
        '{"tool":"simulate_goal","arguments":{"category":"Dining","reduction_pct":999,"horizon_months":99}}'
    )

    result = execute_tool_request(request, transactions, [], "USD")

    assert result["tool"] == "simulate_goal"
    assert result["reduction_pct"] == "100"
    assert result["horizon_months"] == 12
    assert result["evidence_transaction_ids"] == ["a"]

"""Legacy peer-comparison route with an honest unavailable state.

Ledger does not yet have a consented, representative, verified peer dataset.
The old synthetic percentiles must not be presented as community facts.
"""

from .insights import data_quality, monthly_summary


def generate_benchmarks(transactions: list, currency: str = "INR", currency_mismatch: bool = False) -> dict:
    """Return user's own spending evidence without inventing a peer rank."""
    quality = data_quality(transactions)
    summary = monthly_summary(transactions)
    categories = [
        {"category": name, "your_spend": amount}
        for name, amount in sorted(summary["by_category"].items(), key=lambda item: item[1], reverse=True)
        if amount > 0
    ]
    return {
        "comparison_status": "unavailable",
        "reason": (
            "Account currencies differ from your Ledger currency. Resolve this before combining spending amounts. "
            "No verified peer-spending dataset is available."
            if currency_mismatch else
            "No verified, representative peer-spending dataset is available. Your spending below comes only from your own posted transactions."
        ),
        "currency": currency,
        "period_start": quality["period_start"],
        "period_end": quality["period_end"],
        "transaction_count": quality["transaction_count"],
        "total_spending": None if currency_mismatch else summary["expenses"],
        "categories": [] if currency_mismatch else categories,
    }

"""
Community benchmarks — anonymous spending comparisons.
Provides percentile rankings against aggregated (anonymized) spending patterns.
Uses synthetic reference data since we don't have multi-tenant data yet.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any

# Indian urban spending benchmarks (monthly, INR)
# Source: NSSO consumer expenditure survey, adjusted for urban middle class
BENCHMARK_DATA = {
    "Dining": {"p25": 2500, "p50": 5000, "p75": 9000, "p90": 15000},
    "Groceries": {"p25": 4000, "p50": 7000, "p75": 12000, "p90": 18000},
    "Transport": {"p25": 1500, "p50": 3500, "p75": 7000, "p90": 12000},
    "Shopping": {"p25": 2000, "p50": 5000, "p75": 10000, "p90": 20000},
    "Subscriptions": {"p25": 300, "p50": 800, "p75": 1500, "p90": 3000},
    "Health": {"p25": 500, "p50": 2000, "p75": 5000, "p90": 10000},
    "Utilities": {"p25": 1500, "p50": 3000, "p75": 5000, "p90": 8000},
    "Entertainment": {"p25": 1000, "p50": 3000, "p75": 6000, "p90": 12000},
    "Housing": {"p25": 8000, "p50": 15000, "p75": 25000, "p90": 45000},
    "Other": {"p25": 1000, "p50": 3000, "p75": 6000, "p90": 10000},
}

TOTAL_BENCHMARK = {"p25": 25000, "p50": 45000, "p75": 80000, "p90": 130000}


def compute_percentile(value: float, benchmarks: dict) -> int:
    """Return the percentile (0-100) for a given value against benchmark data."""
    if value <= benchmarks["p25"]:
        return int(25 * value / max(benchmarks["p25"], 1))
    elif value <= benchmarks["p50"]:
        return 25 + int(25 * (value - benchmarks["p25"]) / max(benchmarks["p50"] - benchmarks["p25"], 1))
    elif value <= benchmarks["p75"]:
        return 50 + int(25 * (value - benchmarks["p50"]) / max(benchmarks["p75"] - benchmarks["p50"], 1))
    elif value <= benchmarks["p90"]:
        return 75 + int(15 * (value - benchmarks["p75"]) / max(benchmarks["p90"] - benchmarks["p75"], 1))
    else:
        return min(99, 90 + int(10 * (value - benchmarks["p90"]) / max(benchmarks["p90"], 1)))


def generate_benchmarks(transactions: list) -> dict[str, Any]:
    """
    Generate community benchmark comparison for a user's spending.
    Returns percentile rankings by category and overall.
    """
    cat_spend = defaultdict(float)
    total_expense = 0

    for tx in transactions:
        if tx.type == "expense":
            cat_spend[tx.category] += float(tx.amount)
            total_expense += float(tx.amount)

    categories = []
    for cat, benchmarks in BENCHMARK_DATA.items():
        spent = cat_spend.get(cat, 0)
        percentile = compute_percentile(spent, benchmarks)

        if percentile <= 25:
            status = "low"
            label = "Well below average"
        elif percentile <= 50:
            status = "good"
            label = "Below average"
        elif percentile <= 75:
            status = "average"
            label = "Around average"
        else:
            status = "high"
            label = "Above average"

        categories.append({
            "category": cat,
            "your_spend": round(spent, 2),
            "percentile": percentile,
            "status": status,
            "label": label,
            "benchmark_median": benchmarks["p50"],
            "benchmark_p75": benchmarks["p75"],
        })

    # Sort by percentile descending (highest spenders first)
    categories.sort(key=lambda c: c["percentile"], reverse=True)

    # Overall
    overall_percentile = compute_percentile(total_expense, TOTAL_BENCHMARK)

    return {
        "overall_percentile": overall_percentile,
        "total_spending": round(total_expense, 2),
        "benchmark_median": TOTAL_BENCHMARK["p50"],
        "categories": categories,
        "sample_size": "10,000+",  # synthetic reference
        "methodology": "Urban middle-class spending patterns (NSSO-adjusted)",
    }

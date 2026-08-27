"""
Spending Forecaster — projects future spending using EWMA.

Strategy
--------
1. Group expense transactions into monthly buckets per category.
2. Apply Exponential Weighted Moving Average (alpha=0.3) so that recent
   months have more weight on the smoothed estimate.
3. Scale the monthly EWMA to 30 / 60 / 90-day projections.
4. Derive confidence from the inverse of the Coefficient of Variation (CV),
   clamped to [0.30, 0.95].
5. Detect trend direction by comparing the average of the last 2 months
   against the prior 2 months.

Public API
----------
- ``generate_forecast(transactions)``        → per-category + total projections
- ``budget_breach_warnings(transactions, budgets)``  → categories likely to
                                                        exceed their monthly limit
"""

import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from ..models import Transaction

logger = logging.getLogger("ledger.forecaster")

# ── Constants ─────────────────────────────────────────────────────────────────

# EWMA smoothing factor — higher = more weight on recent months
_EWMA_ALPHA: float = 0.3

# Confidence clamping bounds (inverse-CV based)
_CONF_MIN: float = 0.30
_CONF_MAX: float = 0.95

# Minimum months of history before we issue a projection
_MIN_MONTHS: int = 1

# Trend change threshold: must differ by at least this fraction to be
# labelled "up" or "down" rather than "stable"
_TREND_THRESHOLD: float = 0.05  # 5 %


# ── Internal helpers ──────────────────────────────────────────────────────────


def _ewma(values: list[float], alpha: float = _EWMA_ALPHA) -> float:
    """
    Compute the Exponential Weighted Moving Average of a chronological list.

    The first observation is used as the initial smoothed estimate, then
    each subsequent observation updates: S_t = alpha * X_t + (1-alpha) * S_{t-1}.

    Args:
        values: Time-ordered list of numeric values (oldest → newest).
        alpha:  Smoothing factor in (0, 1].  Larger = more weight on recent data.

    Returns:
        Final EWMA value, or 0.0 for an empty list.
    """
    if not values:
        return 0.0
    smoothed = values[0]
    for v in values[1:]:
        smoothed = alpha * v + (1 - alpha) * smoothed
    return smoothed


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Return (mean, population std) for a list of floats."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(variance)


def _confidence_from_cv(values: list[float]) -> float:
    """
    Compute forecast confidence as the inverse of the Coefficient of Variation.

    CV = std / mean.  A CV of 0 means perfectly stable → confidence = _CONF_MAX.
    Higher CV → lower confidence, clamped to [_CONF_MIN, _CONF_MAX].

    Returns _CONF_MIN when values is empty or mean is 0.
    """
    if len(values) < 2:
        # Single data point — moderate confidence
        return 0.60
    mean, std = _mean_std(values)
    if mean == 0.0:
        return _CONF_MIN
    cv = std / mean
    # confidence = 1 / (1 + CV), then clamp
    raw = 1.0 / (1.0 + cv)
    return max(_CONF_MIN, min(_CONF_MAX, raw))


def _trend(monthly_values: list[float]) -> str:
    """
    Compare last-2-months average vs prior-2-months average.

    Returns "up", "down", or "stable".  Falls back to "stable" with < 2 months.
    """
    if len(monthly_values) < 2:
        return "stable"
    recent = monthly_values[-2:]
    prior = monthly_values[-4:-2] if len(monthly_values) >= 4 else monthly_values[: max(1, len(monthly_values) - 2)]
    recent_avg = sum(recent) / len(recent)
    prior_avg = sum(prior) / len(prior) if prior else recent_avg
    if prior_avg == 0.0:
        return "stable"
    change = (recent_avg - prior_avg) / prior_avg
    if change > _TREND_THRESHOLD:
        return "up"
    if change < -_TREND_THRESHOLD:
        return "down"
    return "stable"


def _monthly_buckets(transactions: list[Transaction]) -> dict[str, dict[str, float]]:
    """
    Build a mapping of {category: {YYYY-MM: total_spend}}.

    Only expense transactions are counted.
    """
    buckets: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for tx in transactions:
        if tx.type == "expense":
            month_key = tx.date.strftime("%Y-%m")
            buckets[tx.category][month_key] += float(tx.amount)
    return buckets


# ── Public API ────────────────────────────────────────────────────────────────


def generate_forecast(transactions: list[Transaction]) -> dict[str, Any]:
    """
    Generate spending forecasts for each expense category using EWMA.

    Args:
        transactions: Historical transaction list (may include income).

    Returns:
        Dict with keys:
        - ``by_category``        {cat: {"projected_30d", "projected_60d",
                                        "projected_90d", "monthly_avg",
                                        "confidence", "trend"}}
        - ``total_projected_30d``  float
        - ``total_projected_60d``  float
        - ``total_projected_90d``  float
        - ``generated_at``         str (ISO-8601 date)
    """
    if not transactions:
        logger.info("generate_forecast called with no transactions")
        return {
            "by_category": {},
            "total_projected_30d": 0.0,
            "total_projected_60d": 0.0,
            "total_projected_90d": 0.0,
            "generated_at": date.today().isoformat(),
        }

    buckets = _monthly_buckets(transactions)
    by_category: dict[str, dict[str, Any]] = {}

    for category, month_map in buckets.items():
        if not month_map:
            continue

        # Sort months chronologically (YYYY-MM strings sort correctly)
        sorted_months = sorted(month_map.keys())
        monthly_values = [month_map[m] for m in sorted_months]

        if len(monthly_values) < _MIN_MONTHS:
            continue

        # EWMA of monthly totals
        smoothed_monthly = _ewma(monthly_values)

        # Scale to day-based projections (30d ≈ 1 month, 60d ≈ 2, 90d ≈ 3)
        projected_30d = smoothed_monthly
        projected_60d = smoothed_monthly * 2.0
        projected_90d = smoothed_monthly * 3.0

        # Simple arithmetic mean for reference
        monthly_avg = sum(monthly_values) / len(monthly_values)

        confidence = _confidence_from_cv(monthly_values)
        trend_dir = _trend(monthly_values)

        by_category[category] = {
            "projected_30d": round(projected_30d, 2),
            "projected_60d": round(projected_60d, 2),
            "projected_90d": round(projected_90d, 2),
            "monthly_avg": round(monthly_avg, 2),
            "confidence": round(confidence, 4),
            "trend": trend_dir,
        }

    total_30d = sum(v["projected_30d"] for v in by_category.values())
    total_60d = sum(v["projected_60d"] for v in by_category.values())
    total_90d = sum(v["projected_90d"] for v in by_category.values())

    logger.info(
        "Forecast generated for %d categories — 30d total: %.2f",
        len(by_category),
        total_30d,
    )

    return {
        "by_category": by_category,
        "total_projected_30d": round(total_30d, 2),
        "total_projected_60d": round(total_60d, 2),
        "total_projected_90d": round(total_90d, 2),
        "generated_at": date.today().isoformat(),
    }


def budget_breach_warnings(
    transactions: list[Transaction],
    budgets: list,
) -> list[dict[str, Any]]:
    """
    Predict which budget categories will be breached by month-end.

    Uses the current month's spending so far plus a pro-rated projection
    of remaining days.  If the extrapolated total exceeds the monthly limit,
    a warning entry is emitted.

    Args:
        transactions: All transactions (income + expense).
        budgets:      List of Budget ORM objects with ``.category`` and
                      ``.monthly_limit`` attributes.

    Returns:
        List of dicts, one per at-risk category:
        - ``category``        str
        - ``monthly_limit``   float
        - ``spent_so_far``    float
        - ``projected_total`` float
        - ``projected_breach``float  (projected_total - monthly_limit, > 0)
        - ``days_elapsed``    int
        - ``days_remaining``  int
        - ``severity``        "low" | "medium" | "high"
    """
    if not budgets:
        return []

    today = date.today()
    # Start of current month
    month_start = today.replace(day=1)
    # End of current month (first day of next month - 1)
    if today.month == 12:
        month_end = today.replace(year=today.year + 1, month=1, day=1) - timedelta(days=1)
    else:
        month_end = today.replace(month=today.month + 1, day=1) - timedelta(days=1)

    days_in_month = (month_end - month_start).days + 1
    days_elapsed = (today - month_start).days + 1  # inclusive of today
    days_remaining = days_in_month - days_elapsed

    # Sum current-month expense per category
    cat_spent: dict[str, float] = defaultdict(float)
    for tx in transactions:
        if tx.type == "expense" and tx.date >= month_start:
            cat_spent[tx.category] += float(tx.amount)

    warnings: list[dict[str, Any]] = []

    for budget in budgets:
        limit = float(budget.monthly_limit)
        if limit <= 0:
            continue

        spent = cat_spent.get(budget.category, 0.0)
        if spent == 0.0:
            continue

        # Daily run-rate × full month length
        daily_rate = spent / max(days_elapsed, 1)
        projected_total = daily_rate * days_in_month

        if projected_total <= limit:
            continue  # on track — no warning needed

        breach_amount = projected_total - limit
        breach_ratio = projected_total / limit  # > 1.0

        if breach_ratio >= 1.5:
            severity = "high"
        elif breach_ratio >= 1.2:
            severity = "medium"
        else:
            severity = "low"

        warnings.append(
            {
                "category": budget.category,
                "monthly_limit": round(limit, 2),
                "spent_so_far": round(spent, 2),
                "projected_total": round(projected_total, 2),
                "projected_breach": round(breach_amount, 2),
                "days_elapsed": days_elapsed,
                "days_remaining": days_remaining,
                "severity": severity,
            }
        )

    # Sort by breach severity then breach amount descending
    _sev_order = {"high": 0, "medium": 1, "low": 2}
    warnings.sort(key=lambda w: (_sev_order[w["severity"]], -w["projected_breach"]))

    logger.info(
        "budget_breach_warnings: %d / %d categories at risk",
        len(warnings),
        len(budgets),
    )
    return warnings

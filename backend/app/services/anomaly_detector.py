"""
Anomaly Detector — detects unusual spending patterns in transactions.
Uses IQR-based outlier detection per category + rolling z-score for velocity spikes.

Detection strategies
--------------------
1. ``large_purchase``   — per-category IQR fence (Q3 + 1.5*IQR) AND > 3× category median.
                          Requires at least 5 transactions in the category to reduce false positives.
2. ``velocity_spike``   — daily expense totals that exceed mean + 2.5σ are flagged.
3. ``duplicate_suspect``— same (amount, category) pair within a 48-hour window but different IDs.

Results are returned sorted by severity (high → medium → low) then by date descending.
"""

import logging
import math
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from ..models import Transaction

logger = logging.getLogger("ledger.anomaly")

# ── Anomaly type registry ─────────────────────────────────────────────────────
ANOMALY_TYPES: dict[str, str] = {
    "large_purchase": "Unusually large purchase",
    "velocity_spike": "Sudden spending spike",
    "category_spike": "Category spending unusually high",
    "duplicate_suspect": "Possible duplicate transaction",
    "unusual_merchant": "Merchant not seen before",
    "late_night": "Late-night high-value transaction",  # future use
}

# Severity ordering for sorting (lower index = higher priority)
_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

# Minimum samples required in a category before IQR flagging kicks in
_MIN_CATEGORY_SAMPLES: int = 5

# IQR fence multiplier and median multiplier thresholds
_IQR_FENCE_MULTIPLIER: float = 1.5
_MEDIAN_MULTIPLIER: float = 3.0

# Velocity spike threshold: mean + N × std
_VELOCITY_SIGMA: float = 2.5

# Duplicate detection window (hours)
_DUPLICATE_WINDOW_HOURS: int = 48


# ── Internal helpers ──────────────────────────────────────────────────────────


def _sorted_floats(values: list[float]) -> list[float]:
    """Return a new sorted list of floats."""
    return sorted(values)


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """
    Linear-interpolation percentile on a pre-sorted list.

    Args:
        sorted_vals: Ascending-sorted float list (must be non-empty).
        pct:         Percentile in [0, 100].

    Returns:
        Interpolated percentile value.
    """
    n = len(sorted_vals)
    if n == 1:
        return sorted_vals[0]
    idx = (pct / 100) * (n - 1)
    lo = int(idx)
    hi = lo + 1
    if hi >= n:
        return sorted_vals[-1]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _median(sorted_vals: list[float]) -> float:
    """Return the median of a pre-sorted list."""
    return _percentile(sorted_vals, 50.0)


def _mean_std(values: list[float]) -> tuple[float, float]:
    """
    Compute mean and population standard deviation.

    Returns:
        Tuple of (mean, std). std is 0.0 when len(values) < 2.
    """
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(variance)


def _severity_from_ratio(ratio: float) -> str:
    """
    Map an excess ratio (observed / fence) to a severity label.

    - ratio < 1.5  → low
    - ratio < 2.5  → medium
    - ratio >= 2.5 → high
    """
    if ratio >= 2.5:
        return "high"
    if ratio >= 1.5:
        return "medium"
    return "low"


# ── Anomaly detection strategies ─────────────────────────────────────────────


def _detect_large_purchases(
    expense_txns: list[Transaction],
) -> list[dict[str, Any]]:
    """
    Flag transactions whose amount exceeds the per-category IQR upper fence
    AND is more than 3× the category median.

    Requires at least ``_MIN_CATEGORY_SAMPLES`` transactions per category.
    """
    # Group by category
    by_category: dict[str, list[Transaction]] = defaultdict(list)
    for tx in expense_txns:
        by_category[tx.category].append(tx)

    anomalies: list[dict[str, Any]] = []

    for category, txns in by_category.items():
        if len(txns) < _MIN_CATEGORY_SAMPLES:
            # Not enough data to establish a reliable baseline
            logger.debug(
                "Skipping IQR check for category '%s' — only %d samples (min %d)",
                category,
                len(txns),
                _MIN_CATEGORY_SAMPLES,
            )
            continue

        amounts = _sorted_floats([float(tx.amount) for tx in txns])
        q1 = _percentile(amounts, 25.0)
        q3 = _percentile(amounts, 75.0)
        iqr = q3 - q1
        fence = q3 + _IQR_FENCE_MULTIPLIER * iqr
        med = _median(amounts)
        threshold = med * _MEDIAN_MULTIPLIER

        for tx in txns:
            amount = float(tx.amount)
            if amount > fence and amount > threshold:
                ratio = amount / max(fence, 1.0)
                severity = _severity_from_ratio(ratio)
                anomalies.append(
                    {
                        "transaction_id": tx.id,
                        "anomaly_type": "large_purchase",
                        "severity": severity,
                        "message": (
                            f"{ANOMALY_TYPES['large_purchase']}: INR {amount:,.2f} in {category} "
                            f"(category fence INR {fence:,.2f}, median INR {med:,.2f})"
                        ),
                        "expected_range": {"min": float(q1), "max": float(fence)},
                        "date": tx.date.isoformat(),
                        "amount": amount,
                        "category": category,
                    }
                )

    return anomalies


def _detect_velocity_spikes(
    expense_txns: list[Transaction],
) -> list[dict[str, Any]]:
    """
    Detect days where total spending exceeded mean_daily + 2.5 × std_daily.

    All transactions on flagged days are surfaced as ``velocity_spike`` anomalies.
    Requires at least 3 distinct days of spending to compute a meaningful baseline.
    """
    # Aggregate daily expense totals
    daily_totals: dict[date, float] = defaultdict(float)
    daily_txns: dict[date, list[Transaction]] = defaultdict(list)

    for tx in expense_txns:
        daily_totals[tx.date] += float(tx.amount)
        daily_txns[tx.date].append(tx)

    if len(daily_totals) < 3:
        return []

    daily_values = list(daily_totals.values())
    mean_daily, std_daily = _mean_std(daily_values)
    spike_threshold = mean_daily + _VELOCITY_SIGMA * std_daily

    if std_daily == 0.0:
        # All days identical — no spike possible
        return []

    anomalies: list[dict[str, Any]] = []
    for day, total in daily_totals.items():
        if total > spike_threshold:
            ratio = total / max(spike_threshold, 1.0)
            severity = _severity_from_ratio(ratio)
            # Flag every transaction on this day
            for tx in daily_txns[day]:
                anomalies.append(
                    {
                        "transaction_id": tx.id,
                        "anomaly_type": "velocity_spike",
                        "severity": severity,
                        "message": (
                            f"{ANOMALY_TYPES['velocity_spike']}: day total INR {total:,.2f} "
                            f"vs typical INR {mean_daily:,.2f} ± {std_daily:,.2f}"
                        ),
                        "expected_range": {
                            "min": max(0.0, mean_daily - std_daily),
                            "max": float(spike_threshold),
                        },
                        "date": tx.date.isoformat(),
                        "amount": float(tx.amount),
                        "category": tx.category,
                    }
                )

    return anomalies


def _detect_duplicate_suspects(
    expense_txns: list[Transaction],
) -> list[dict[str, Any]]:
    """
    Flag pairs of transactions that share the same amount AND category within 48 hours.

    Only the *later* transaction in each pair is surfaced to avoid double-reporting.
    """
    # Sort ascending by date, then by created_at for determinism
    sorted_txns = sorted(expense_txns, key=lambda t: (t.date, t.created_at))
    anomalies: list[dict[str, Any]] = []
    flagged_ids: set[str] = set()
    window = timedelta(hours=_DUPLICATE_WINDOW_HOURS)

    for i, tx_a in enumerate(sorted_txns):
        if tx_a.id in flagged_ids:
            continue
        for tx_b in sorted_txns[i + 1 :]:
            # Break early once the time window is exceeded
            if (tx_b.date - tx_a.date) > window:
                break
            if tx_b.id == tx_a.id or tx_b.id in flagged_ids:
                continue
            if tx_b.amount == tx_a.amount and tx_b.category == tx_a.category:
                flagged_ids.add(tx_b.id)
                anomalies.append(
                    {
                        "transaction_id": tx_b.id,
                        "anomaly_type": "duplicate_suspect",
                        "severity": "medium",
                        "message": (
                            f"{ANOMALY_TYPES['duplicate_suspect']}: INR {float(tx_b.amount):,.2f} "
                            f"in {tx_b.category} appears within 48 h of transaction {tx_a.id[:8]}…"
                        ),
                        "expected_range": None,
                        "date": tx_b.date.isoformat(),
                        "amount": float(tx_b.amount),
                        "category": tx_b.category,
                    }
                )

    return anomalies


# ── De-duplication ────────────────────────────────────────────────────────────


def _deduplicate(anomalies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove exact duplicates (same transaction_id + anomaly_type).
    Keep the highest-severity entry when a transaction appears more than once
    for the same anomaly type.
    """
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for a in anomalies:
        key = (a["transaction_id"], a["anomaly_type"])
        if key not in seen:
            seen[key] = a
        else:
            # Prefer higher severity
            if _SEVERITY_ORDER[a["severity"]] < _SEVERITY_ORDER[seen[key]["severity"]]:
                seen[key] = a
    return list(seen.values())


# ── Public API ────────────────────────────────────────────────────────────────


def detect_anomalies(transactions: list[Transaction]) -> list[dict[str, Any]]:
    """
    Run all anomaly detection strategies against a list of transactions.

    Only expense-type transactions are analysed.  Results are de-duplicated
    and sorted by severity (high first) then date descending.

    Args:
        transactions: All transactions to analyse (income + expense are accepted;
                      income is silently ignored).

    Returns:
        List of anomaly dicts, each with keys:
        - ``transaction_id``  (str)
        - ``anomaly_type``    (str, one of ANOMALY_TYPES keys)
        - ``severity``        ("low" | "medium" | "high")
        - ``message``         (str, human-readable explanation)
        - ``expected_range``  ({"min": float, "max": float} | None)
        - ``date``            (str, ISO-8601 date)
        - ``amount``          (float)
        - ``category``        (str)
    """
    if not transactions:
        logger.info("detect_anomalies called with no transactions — returning empty list")
        return []

    expense_txns = [t for t in transactions if t.type == "expense"]
    if not expense_txns:
        logger.info("No expense transactions found — skipping anomaly detection")
        return []

    logger.info(
        "Running anomaly detection on %d expense transactions (out of %d total)",
        len(expense_txns),
        len(transactions),
    )

    anomalies: list[dict[str, Any]] = []

    try:
        anomalies.extend(_detect_large_purchases(expense_txns))
    except Exception:
        logger.exception("Error in large_purchase detection — skipping")

    try:
        anomalies.extend(_detect_velocity_spikes(expense_txns))
    except Exception:
        logger.exception("Error in velocity_spike detection — skipping")

    try:
        anomalies.extend(_detect_duplicate_suspects(expense_txns))
    except Exception:
        logger.exception("Error in duplicate_suspect detection — skipping")

    # De-duplicate and sort: severity ASC (high=0), then date DESC
    anomalies = _deduplicate(anomalies)
    anomalies.sort(
        key=lambda a: (_SEVERITY_ORDER[a["severity"]], a["date"]),
        # date desc = reverse on secondary; severity asc on primary handled via tuple
    )
    # Secondary sort on date must be descending — re-sort with compound key
    anomalies.sort(key=lambda a: (_SEVERITY_ORDER[a["severity"]], [-ord(c) for c in a["date"]]))

    # Simpler, correct two-pass sort:
    anomalies.sort(key=lambda a: a["date"], reverse=True)
    anomalies.sort(key=lambda a: _SEVERITY_ORDER[a["severity"]])

    logger.info("Anomaly detection complete — %d anomalies found", len(anomalies))
    return anomalies

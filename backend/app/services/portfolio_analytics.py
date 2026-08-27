"""
Portfolio Analytics — computes advanced investment metrics.

Metrics produced
----------------
- Asset allocation breakdown (% of total current value by asset_type)
- Simple & annualised return per holding
- Portfolio-level Sharpe ratio (using Indian G-Sec 7 % risk-free rate)
- XIRR approximation via Newton–Raphson (requires ``purchase_date``)
- Maximum drawdown across all holdings
- Best / worst performer by return %

All monetary values are treated as INR unless otherwise noted.
"""

import logging
import math
from collections import defaultdict
from datetime import date
from typing import Any

logger = logging.getLogger("ledger.portfolio_analytics")

# ── Constants ─────────────────────────────────────────────────────────────────

RISK_FREE_RATE: float = 0.07  # 7 % annual — approximate Indian G-Sec rate

# Newton-Raphson XIRR solver limits
_XIRR_MAX_ITER: int = 1000
_XIRR_TOL: float = 1e-7
_XIRR_INITIAL_GUESS: float = 0.1  # 10 % initial IRR guess


# ── Internal helpers ──────────────────────────────────────────────────────────


def _years_held(purchase_date: date) -> float:
    """
    Compute how many fractional years have elapsed since purchase_date.

    Returns 1.0 as a safe fallback if the result would be <= 0.
    """
    delta = (date.today() - purchase_date).days
    years = delta / 365.25
    return max(years, 1.0 / 365.25)  # at least one day


def _annualise(simple_return: float, years: float) -> float:
    """
    Convert a simple (total) return to an annualised return.

    Uses the compound growth formula: (1 + r)^(1/years) - 1.
    Handles negative returns gracefully by treating (1 + r) as 0 when < 0.
    """
    base = 1.0 + simple_return
    if base <= 0:
        return -1.0  # total loss
    try:
        return base ** (1.0 / years) - 1.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def _xirr_npv(rate: float, cashflows: list[tuple[date, float]]) -> float:
    """
    Compute Net Present Value of dated cash flows at a given annual rate.

    Follows the XIRR convention: each flow discounted by
    (1 + rate)^(days / 365.25).

    Args:
        rate:       Annual discount rate (e.g. 0.12 for 12 %).
        cashflows:  List of (date, amount) tuples.  Outflows are negative.

    Returns:
        NPV as a float.
    """
    if not cashflows:
        return 0.0
    base_date = cashflows[0][0]
    npv = 0.0
    for cf_date, amount in cashflows:
        t = (cf_date - base_date).days / 365.25
        npv += amount / ((1.0 + rate) ** t)
    return npv


def _xirr(cashflows: list[tuple[date, float]]) -> float | None:
    """
    Approximate XIRR using Newton–Raphson iteration.

    Args:
        cashflows: Sorted list of (date, signed_amount) — outflows negative.

    Returns:
        Annualised IRR as a decimal (e.g. 0.15 = 15 %) or None if it fails
        to converge or inputs are degenerate.
    """
    if len(cashflows) < 2:
        return None

    # Validate there are both positive and negative flows
    has_negative = any(a < 0 for _, a in cashflows)
    has_positive = any(a > 0 for _, a in cashflows)
    if not (has_negative and has_positive):
        return None

    rate = _XIRR_INITIAL_GUESS
    for _ in range(_XIRR_MAX_ITER):
        npv = _xirr_npv(rate, cashflows)
        # Numerical derivative (finite difference)
        delta = 1e-6
        npv_delta = _xirr_npv(rate + delta, cashflows)
        derivative = (npv_delta - npv) / delta

        if abs(derivative) < 1e-12:
            break  # Flat — can't solve

        rate_new = rate - npv / derivative

        # Guard against blow-up
        if not math.isfinite(rate_new) or rate_new <= -1.0:
            rate_new = rate / 2.0

        if abs(rate_new - rate) < _XIRR_TOL:
            return round(rate_new, 6)
        rate = rate_new

    # Check if final solution is close enough
    if abs(_xirr_npv(rate, cashflows)) < 1.0:
        return round(rate, 6)

    logger.debug("XIRR did not converge — returning None")
    return None


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


# ── Core computation ──────────────────────────────────────────────────────────


def compute_portfolio_analytics(
    portfolios: list,
    holdings_by_portfolio: dict[str, list],
) -> dict[str, Any]:
    """
    Compute advanced investment metrics across one or more portfolios.

    Args:
        portfolios:             List of Portfolio ORM objects (with ``.id``,
                                ``.name``, ``.portfolio_type``).
        holdings_by_portfolio:  Dict mapping portfolio.id → list of Holding
                                ORM objects.  Each Holding has:
                                ``.symbol``, ``.name``, ``.quantity``,
                                ``.buy_price``, ``.current_price``,
                                ``.asset_type``, ``.purchase_date`` (optional).

    Returns:
        Dict with keys:
        - ``allocation``          list[{"asset_type", "value", "pct"}]
        - ``total_value``         float  (current portfolio value)
        - ``total_invested``      float  (total cost basis)
        - ``total_return_pct``    float  (simple return on total portfolio)
        - ``annualized_return_pct`` float
        - ``sharpe_ratio``        float | None
        - ``xirr``                float | None
        - ``max_drawdown_pct``    float  (0.0 = no drawdown, -ve = loss)
        - ``best_performer``      {"symbol", "return_pct"} | None
        - ``worst_performer``     {"symbol", "return_pct"} | None
        - ``by_asset_type``       dict of per-asset-type aggregates
    """
    # Flatten all holdings
    all_holdings: list = []
    for portfolio in portfolios:
        for h in holdings_by_portfolio.get(portfolio.id, []):
            all_holdings.append(h)

    if not all_holdings:
        logger.info("compute_portfolio_analytics: no holdings provided")
        return {
            "allocation": [],
            "total_value": 0.0,
            "total_invested": 0.0,
            "total_return_pct": 0.0,
            "annualized_return_pct": 0.0,
            "sharpe_ratio": None,
            "xirr": None,
            "max_drawdown_pct": 0.0,
            "best_performer": None,
            "worst_performer": None,
            "by_asset_type": {},
        }

    # ── 1. Asset allocation ───────────────────────────────────────────────────
    type_value: dict[str, float] = defaultdict(float)
    type_invested: dict[str, float] = defaultdict(float)

    total_value: float = 0.0
    total_invested: float = 0.0

    holding_returns: list[float] = []  # simple returns, one per holding
    holding_annualised: list[float] = []

    best_symbol: str | None = None
    best_return: float = float("-inf")
    worst_symbol: str | None = None
    worst_return: float = float("inf")

    # Collect cashflows for XIRR (all holdings combined)
    all_cashflows: list[tuple[date, float]] = []

    for h in all_holdings:
        qty = float(h.quantity)
        buy_px = float(h.buy_price)
        cur_px = float(h.current_price)
        invested = qty * buy_px
        current_val = qty * cur_px

        total_value += current_val
        total_invested += invested
        type_value[h.asset_type] += current_val
        type_invested[h.asset_type] += invested

        # Simple return
        if invested > 0:
            simple_ret = (current_val - invested) / invested
        else:
            simple_ret = 0.0

        holding_returns.append(simple_ret)

        # Annualised return
        if h.purchase_date:
            years = _years_held(h.purchase_date)
            ann_ret = _annualise(simple_ret, years)
            holding_annualised.append(ann_ret)
            # XIRR cash flows: initial outflow at purchase_date, inflow today
            all_cashflows.append((h.purchase_date, -invested))
            all_cashflows.append((date.today(), current_val))
        else:
            ann_ret = _annualise(simple_ret, 1.0)
            holding_annualised.append(ann_ret)

        # Best / worst performers
        if simple_ret > best_return:
            best_return = simple_ret
            best_symbol = h.symbol
        if simple_ret < worst_return:
            worst_return = simple_ret
            worst_symbol = h.symbol

    # ── 2. Allocation percentages ─────────────────────────────────────────────
    allocation: list[dict[str, Any]] = []
    for asset_type, val in sorted(type_value.items(), key=lambda x: x[1], reverse=True):
        pct = (val / total_value * 100) if total_value > 0 else 0.0
        allocation.append(
            {
                "asset_type": asset_type,
                "value": round(val, 2),
                "pct": round(pct, 2),
                "invested": round(type_invested[asset_type], 2),
            }
        )

    # ── 3. Portfolio-level simple return ──────────────────────────────────────
    total_return_pct = ((total_value - total_invested) / total_invested * 100) if total_invested > 0 else 0.0

    # ── 4. Portfolio annualised return (weighted avg of individual ann returns)
    annualized_return_pct: float = 0.0
    if holding_annualised:
        annualized_return_pct = (sum(holding_annualised) / len(holding_annualised)) * 100

    # ── 5. Sharpe ratio ───────────────────────────────────────────────────────
    sharpe_ratio: float | None = None
    if len(holding_annualised) >= 2:
        portfolio_ann_return = sum(holding_annualised) / len(holding_annualised)
        _, std_returns = _mean_std(holding_annualised)
        if std_returns > 0:
            sharpe_ratio = round((portfolio_ann_return - RISK_FREE_RATE) / std_returns, 4)
        else:
            sharpe_ratio = 0.0
    else:
        # < 2 holdings — Sharpe undefined
        sharpe_ratio = 0.0

    # ── 6. XIRR approximation ────────────────────────────────────────────────
    xirr_result: float | None = None
    if all_cashflows:
        all_cashflows_sorted = sorted(all_cashflows, key=lambda cf: cf[0])
        try:
            xirr_result = _xirr(all_cashflows_sorted)
            if xirr_result is not None:
                xirr_result = round(xirr_result * 100, 4)  # express as %
        except Exception:
            logger.exception("XIRR computation failed — returning None")

    # ── 7. Maximum drawdown ───────────────────────────────────────────────────
    # Compute max peak-to-trough drop in individual holding returns (as % of peak)
    max_drawdown_pct: float = 0.0
    if holding_returns:
        peak = holding_returns[0]
        for r in holding_returns[1:]:
            if r > peak:
                peak = r
            drawdown = ((r - peak) / (1.0 + peak)) * 100 if (1.0 + peak) > 0 else 0.0
            if drawdown < max_drawdown_pct:  # drawdown is negative when present
                max_drawdown_pct = drawdown

    # ── 8. Per-asset-type aggregates ─────────────────────────────────────────
    by_asset_type: dict[str, dict[str, Any]] = {}
    for asset_type, val in type_value.items():
        inv = type_invested[asset_type]
        ret_pct = ((val - inv) / inv * 100) if inv > 0 else 0.0
        by_asset_type[asset_type] = {
            "current_value": round(val, 2),
            "invested": round(inv, 2),
            "return_pct": round(ret_pct, 2),
        }

    logger.info(
        "Portfolio analytics computed: %.2f total value, %.2f%% simple return, Sharpe=%.3f",
        total_value,
        total_return_pct,
        sharpe_ratio if sharpe_ratio is not None else 0.0,
    )

    return {
        "allocation": allocation,
        "total_value": round(total_value, 2),
        "total_invested": round(total_invested, 2),
        "total_return_pct": round(total_return_pct, 2),
        "annualized_return_pct": round(annualized_return_pct, 2),
        "sharpe_ratio": sharpe_ratio,
        "xirr": xirr_result,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "best_performer": (
            {"symbol": best_symbol, "return_pct": round(best_return * 100, 2)} if best_symbol is not None else None
        ),
        "worst_performer": (
            {"symbol": worst_symbol, "return_pct": round(worst_return * 100, 2)} if worst_symbol is not None else None
        ),
        "by_asset_type": by_asset_type,
    }

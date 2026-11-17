"""Analytics and insights: credit health, bills, anomalies, forecast, runway, leakage, proactive insights."""

import logging
import time
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..cache import _user_cache_version, llm_cache
from ..config import settings
from ..db import get_db
from ..helpers import _account_currency_mismatch_count, _client_ip, _cloud_ai_allowed, _history_start, _tx_query
from ..models import Account, AuditLog, Budget, RecurringRule, Transaction, User
from ..rate_limit import limiter
from ..schemas import (
    BenchmarkOut,
    CreditHealthOut,
    InsightFeedbackRequest,
    ProactiveInsight,
    ScenarioOut,
    ScenarioRequest,
    UserContext,
)
from ..services.anomaly_detector import detect_anomalies
from ..services.audit import log_event
from ..services.benchmarks import generate_benchmarks
from ..services.bill_negotiator import analyze_bills
from ..services.credit_health import compute_credit_health
from ..services.feedback import aggregate_insight_feedback
from ..services.forecaster import budget_breach_warnings, generate_forecast
from ..services.insights import compare_calendar_periods, compare_periods, data_quality, recurring_payments
from ..services.leakage import detect_leakage
from ..services.notification_policy import apply_notification_policy
from ..services.proactive_insights import apply_insight_frequency, generate_proactive_insights
from ..services.runway import calculate_runway
from ..services.scenarios import calculate_scenario
from ..services.telemetry import record_telemetry

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Credit Health ─────────────────────────────────────────────────────────────
@router.get("/credit-health", response_model=CreditHealthOut)
def credit_health(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id).all()
    accounts = db.query(Account).filter(Account.user_id == user.id, Account.is_active.is_(True)).all()
    db_user = db.get(User, user.id)
    currency = db_user.currency_preference if db_user else "INR"
    return compute_credit_health(
        transactions, accounts=accounts, currency=currency,
        currency_mismatch=bool(_account_currency_mismatch_count(db, user.id)),
    )


# ── Bill Negotiator ───────────────────────────────────────────────────────────
@router.get("/bills/negotiate")
@limiter.limit(settings.insights_rate_limit)
async def negotiate_bills(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id).limit(500).all()
    recurring = recurring_payments(transactions)
    if not recurring:
        return []
    return await analyze_bills(recurring, allow_cloud_ai=_cloud_ai_allowed(db, user.id))


# ── Community Benchmarks ──────────────────────────────────────────────────────
@router.get("/benchmarks", response_model=BenchmarkOut)
def community_benchmarks(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id).all()
    db_user = db.get(User, user.id)
    currency = db_user.currency_preference if db_user else "INR"
    return generate_benchmarks(
        transactions, currency, currency_mismatch=bool(_account_currency_mismatch_count(db, user.id))
    )


# ── Anomaly Detection ─────────────────────────────────────────────────────────
@router.get("/analytics/anomalies")
def get_anomalies(
    range: str | None = Query("3m", pattern="^(this_month|30d|3m|1y|all|current_year)$"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detect anomalous transactions using IQR + velocity spike analysis."""
    db_user = db.get(User, user.id)
    currency = db_user.currency_preference if db_user else "INR"
    cache_key = f"{user.id}:anomalies:{_user_cache_version(db, user.id)}:{range}:{currency}"
    cached = llm_cache.get(cache_key)
    if cached:
        return cached

    start = _history_start(range)
    q = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.status == "posted",
    )
    if start:
        q = q.filter(Transaction.date >= start)
    transactions = q.order_by(Transaction.date.desc()).all()

    anomalies = detect_anomalies(transactions, currency)
    quality = data_quality(transactions)
    result = {
        "items": anomalies,
        "analysis": {
            "period_start": quality.get("period_start"),
            "period_end": quality.get("period_end"),
            "transaction_count": quality.get("transaction_count", 0),
            "coverage": quality.get("coverage", "none"),
            "sufficient": quality.get("coverage") not in ("none", "limited"),
            "warnings": quality.get("warnings", []),
        },
    }
    record_telemetry(
        "analysis.anomalies",
        user_id=user.id,
        parse_success=True,
        evidence_valid=all(bool(item.get("transaction_id")) for item in anomalies),
        metadata={"count": len(anomalies), "coverage": quality.get("coverage", "none"), "warning_count": len(quality.get("warnings", []))},
    )
    llm_cache.put(cache_key, result, ttl=1800)  # 30-min cache
    return result


# ── Spending Forecast ─────────────────────────────────────────────────────────
@router.get("/analytics/forecast")
def get_forecast(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Project 30/60/90-day spending per category using EWMA."""
    cache_key = f"{user.id}:forecast:{_user_cache_version(db, user.id)}"
    cached = llm_cache.get(cache_key)
    if cached:
        return cached

    transactions = _tx_query(db, user.id).limit(1000).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    forecast = generate_forecast(transactions)
    warnings = budget_breach_warnings(transactions, budgets)
    result = {**forecast, "budget_warnings": warnings}
    record_telemetry(
        "analysis.forecast",
        user_id=user.id,
        parse_success=True,
        evidence_valid=True,
        metadata={
            "count": len(forecast.get("by_category", {})),
            "coverage": forecast.get("analysis", {}).get("sufficient", False),
            "warning_count": len(forecast.get("analysis", {}).get("warnings", [])),
        },
    )

    llm_cache.put(cache_key, result, ttl=3600)
    return result


@router.get("/analytics/runway")
def get_runway(
    as_of: date | None = None,
    horizon_months: int = Query(3, ge=1, le=12),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Project reconciled cash with an explicit regular/irregular income range."""
    db_user = db.get(User, user.id)
    currency = db_user.currency_preference if db_user else "INR"
    if _account_currency_mismatch_count(db, user.id):
        return {
            "status": "unavailable",
            "currency": currency,
            "projection": [],
            "data_quality": {"warnings": ["Resolve account currency mismatches before combining balances."]},
        }
    transactions = _tx_query(db, user.id).all()
    accounts = db.query(Account).filter(Account.user_id == user.id).all()
    recurring_rules = db.query(RecurringRule).filter(RecurringRule.user_id == user.id).all()
    return calculate_runway(
        accounts=accounts,
        transactions=transactions,
        recurring_rules=recurring_rules,
        currency=currency,
        income_pattern=db_user.income_pattern if db_user else None,
        as_of=as_of,
        horizon_months=horizon_months,
    )


@router.get("/analytics/leakage")
def get_leakage(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Find cautious merchant and recurring-payment review candidates."""
    transactions = _tx_query(db, user.id).all()
    recurring_rules = db.query(RecurringRule).filter(RecurringRule.user_id == user.id).all()
    return detect_leakage(transactions, recurring_rules)


@router.post("/analytics/scenario", response_model=ScenarioOut)
def run_scenario(
    payload: ScenarioRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Run a deterministic what-if against the user's recent 90-day history."""
    start = date.today() - timedelta(days=90)
    transactions = (
        _tx_query(db, user.id)
        .filter(Transaction.date >= start)
        .order_by(Transaction.date.asc())
        .all()
    )
    return calculate_scenario(
        transactions,
        scenario_type=payload.scenario_type,
        category=payload.category,
        reduction_pct=payload.reduction_pct,
        income_change_pct=payload.income_change_pct,
        one_time_expense=payload.one_time_expense,
        horizon_months=payload.horizon_months,
        target_amount=payload.target_amount,
    )


@router.get("/analytics/compare")
def analytics_compare(
    days: int = Query(30, ge=7, le=365),
    comparison: str | None = Query(None, pattern="^(mom|yoy)$"),
    end: date | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compare two equal-length periods with evidence and sufficiency metadata."""
    transactions = _tx_query(db, user.id).all()
    if comparison:
        return compare_calendar_periods(transactions, comparison=comparison, end_date=end)
    return compare_periods(transactions, end_date=end, days=days)


# ── Proactive Insights (upgraded — with anomaly + forecast context) ────────────
@router.get("/insights/proactive", response_model=list[ProactiveInsight])
@limiter.limit(settings.insights_rate_limit)
async def proactive_insights_v2(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-powered proactive insights with anomaly and forecast injection."""
    # Check cache first (insight_cache_ttl_hours)
    db_user = db.get(User, user.id)
    currency = db_user.currency_preference if db_user else "INR"
    if _account_currency_mismatch_count(db, user.id):
        return []
    cloud_ai_enabled = bool(db_user.cloud_ai_enabled) if db_user else False
    insight_frequency = db_user.insight_frequency if db_user else "daily"
    if insight_frequency == "off":
        return []
    cache_key = f"{user.id}:proactive:{_user_cache_version(db, user.id)}:{currency}:cloud-{int(cloud_ai_enabled)}:frequency-{insight_frequency}"
    cached = llm_cache.get(cache_key)
    if cached and cloud_ai_enabled:
        return cached

    transactions = _tx_query(db, user.id).limit(300).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()

    # Enrich with anomalies and forecast
    anomalies = detect_anomalies(transactions, currency)
    forecast = generate_forecast(transactions)

    started = time.perf_counter()
    result = await generate_proactive_insights(
        transactions,
        budgets,
        anomalies,
        forecast,
        currency,
        allow_ai=cloud_ai_enabled,
        recurring_tolerance=db_user.recurring_tolerance if db_user else "standard",
    )
    result = apply_insight_frequency(result, insight_frequency)
    result = apply_notification_policy(
        result,
        now=datetime.now(UTC),
        start=db_user.quiet_hours_start if db_user else 22,
        end=db_user.quiet_hours_end if db_user else 7,
        daily_cap=db_user.proactive_daily_cap if db_user else 3,
    )
    record_telemetry(
        "insights.generated",
        user_id=user.id,
        latency_ms=(time.perf_counter() - started) * 1000,
        provider="ai" if any(item.get("source") == "model" for item in result) else "rules",
        fallback=not any(item.get("source") == "model" for item in result),
        parse_success=True,
        evidence_valid=all(bool(item.get("evidence")) for item in result),
        metadata={"count": len(result), "evidence_count": sum(len(item.get("evidence", [])) for item in result)},
    )
    llm_cache.put(cache_key, result, ttl=settings.insight_cache_ttl_hours * 3600)
    return result


@router.post("/insights/feedback")
def insight_feedback(
    payload: InsightFeedbackRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record lightweight insight feedback for quality measurement and learning."""
    log_event(
        db,
        user_id=user.id,
        action="feedback",
        resource_type="insight",
        resource_id=payload.insight_id,
        # Keep the audit signal useful without retaining a free-form note that
        # could accidentally contain merchant names or other financial text.
        details={"feedback": payload.feedback, "has_note": bool(payload.note)},
        ip_address=_client_ip(request),
    )
    record_telemetry(
        "insight.feedback",
        user_id=user.id,
        outcome=payload.feedback,
        metadata={"feedback": payload.feedback, "has_note": bool(payload.note)},
    )
    db.commit()
    return {"ok": True, "insight_id": payload.insight_id, "feedback": payload.feedback}


@router.get("/insights/feedback/summary")
def insight_feedback_summary(
    days: int = Query(90, ge=1, le=365),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return user-scoped, text-free feedback counts for insight quality work."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.action == "feedback",
            AuditLog.resource_type == "insight",
            AuditLog.created_at >= since,
        )
        .all()
    )
    result = aggregate_insight_feedback(rows)
    result["window_days"] = days
    return result

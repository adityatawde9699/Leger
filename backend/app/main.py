import asyncio
import base64
import hashlib
import json
import logging
import sys
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import case, inspect, text
from sqlalchemy.orm import Session, selectinload

from .auth import get_current_user
from .config import settings
from .db import Base, SessionLocal, engine, get_db
from .models import (
    Account,
    AIConversation,
    AIMessage,
    AuditLog,
    Budget,
    CategoryCorrection,
    Goal,
    Holding,
    ImportJob,
    MerchantAlias,
    Portfolio,
    RecurringRule,
    Transaction,
    User,
    UserCategory,
    Webhook,
)
from .schemas import (
    AccountIn,
    AccountOut,
    AdvisorRequest,
    AuditLogOut,
    BenchmarkOut,
    BudgetIn,
    BudgetOut,
    BulkDeleteRequest,
    CategorizeBatchRequest,
    CategorizeSingleRequest,
    CategorizeSingleResponse,
    ConversationOut,
    CreditHealthOut,
    DataDeletionRequest,
    GoalIn,
    GoalOut,
    GSTReportOut,
    HoldingIn,
    HoldingOut,
    ImportJobOut,
    ImportPreviewOut,
    InsightFeedbackRequest,
    MerchantAliasIn,
    MerchantAliasOut,
    MessageOut,
    PaginatedTransactions,
    PortfolioIn,
    PortfolioOut,
    ProactiveInsight,
    ProfileStatsOut,
    ReconciliationOut,
    ReconciliationRequest,
    RecurringRuleIn,
    RecurringRuleOut,
    ScenarioOut,
    ScenarioRequest,
    SmsParseRequest,
    SmsWebhookRequest,
    TransactionIn,
    TransactionOut,
    UserCategoryIn,
    UserCategoryOut,
    UserContext,
    UserProfileIn,
    UserProfileOut,
    WebhookIn,
    WebhookOut,
)
from .services.advisor_facts import deterministic_answer
from .services.ai_router import ai_router
from .services.anomaly_detector import detect_anomalies
from .services.audit import get_audit_trail, log_event
from .services.auto_categorizer import categorize_batch, categorize_single
from .services.benchmarks import generate_benchmarks
from .services.bill_negotiator import analyze_bills
from .services.categorization_learner import get_user_overrides, record_correction
from .services.categorizer import CATEGORIES
from .services.credit_health import compute_credit_health
from .services.export import export_csv, export_json, export_tally_xml
from .services.forecaster import budget_breach_warnings, generate_forecast
from .services.gst import generate_gst_report
from .services.insights import (
    SYSTEM_PROMPT,
    build_advisor_context,
    build_analysis_object,
    compare_periods,
    compute_insights,
    data_quality,
    dynamic_budget_suggestions,
    monthly_summary,
    recurring_payments,
)
from .services.portfolio_analytics import compute_portfolio_analytics
from .services.proactive_insights import generate_proactive_insights
from .services.prompt_guard import build_safe_messages, sanitize_user_input
from .services.receipt_ocr import parse_receipt_image
from .services.scenarios import calculate_scenario
from .services.sms_parser import parse_sms
from .services.statements import parse_csv, parse_excel, parse_pdf
from .services.telemetry import record_telemetry
from .services.url_guard import UnsafeURLError, validate_webhook_url


# ── Tiered TTL Cache (L1: in-memory with TTL) ─────────────────────────────────
class TTLCache:
    """LRU cache with per-entry TTL expiry and user-scoped keys."""

    def __init__(self, maxsize: int = 512, default_ttl: int = 3600):
        self._cache: dict[str, dict] = {}
        self.maxsize = maxsize
        self.default_ttl = default_ttl

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, v in self._cache.items() if v["expires"] < now]
        for k in expired:
            del self._cache[k]

    def get(self, key: str):
        entry = self._cache.get(key)
        if not entry:
            return None
        if entry["expires"] < time.time():
            del self._cache[key]
            return None
        # Move to end (LRU)
        val = self._cache.pop(key)
        self._cache[key] = val
        return val["data"]

    def put(self, key: str, value, ttl: int | None = None):
        self._evict_expired()
        if key in self._cache:
            self._cache.pop(key)
        self._cache[key] = {
            "data": value,
            "expires": time.time() + (ttl or self.default_ttl),
        }
        if len(self._cache) > self.maxsize:
            self._cache.pop(next(iter(self._cache)))

    def invalidate_user(self, user_id: str):
        """Invalidate all cache entries for a specific user."""
        keys = [k for k in self._cache if k.startswith(f"{user_id}:")]
        for k in keys:
            del self._cache[k]


llm_cache = TTLCache(maxsize=512, default_ttl=settings.llm_cache_ttl_seconds)


# ── New request schemas ───────────────────────────────────────────────────────
class CategoryCorrectionRequest(BaseModel):
    category: str


# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    stream=sys.stdout,
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ledger.api")

# ── Database bootstrap ────────────────────────────────────────────────────────
# NOTE: In production, use `alembic upgrade head` instead. entrypoint.sh runs the
# same DDL on container start, so set RUN_DB_BOOTSTRAP=false in production to skip
# these redundant inspector round-trips on every cold start.
if settings.run_db_bootstrap:
    Base.metadata.create_all(bind=engine)

    # Ad-hoc migration: Ensure avatar_url exists since Alembic is not configured
    try:
        inspector = inspect(engine)
        if inspector.has_table("users"):
            columns = [col["name"] for col in inspector.get_columns("users")]
            if "avatar_url" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE users ADD COLUMN avatar_url TEXT"))
                    logger.info("Migrated: Added avatar_url to users table.")
        if inspector.has_table("import_jobs"):
            columns = [col["name"] for col in inspector.get_columns("import_jobs")]
            with engine.begin() as conn:
                if "file_extension" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN file_extension VARCHAR(8) DEFAULT ''"))
                    logger.info("Migrated: Added import_jobs.file_extension.")
                if "file_fingerprint" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN file_fingerprint VARCHAR(64)"))
                    logger.info("Migrated: Added import_jobs.file_fingerprint.")
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_import_jobs_file_fingerprint ON import_jobs (file_fingerprint)"))
                if "account_id" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN account_id VARCHAR(36)"))
                    logger.info("Migrated: Added import_jobs.account_id.")
                if "file_content" not in columns:
                    blob_type = "BYTEA" if engine.dialect.name == "postgresql" else "BLOB"
                    conn.execute(text(f"ALTER TABLE import_jobs ADD COLUMN file_content {blob_type}"))
                    logger.info("Migrated: Added import_jobs.file_content.")
                if "total_rows" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN total_rows INTEGER"))
                    logger.info("Migrated: Added import_jobs.total_rows.")
                if "processed_rows" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN processed_rows INTEGER NOT NULL DEFAULT 0"))
                    logger.info("Migrated: Added import_jobs.processed_rows.")
                if "cancel_requested" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT FALSE"))
                    logger.info("Migrated: Added import_jobs.cancel_requested.")
                if "excluded_row_fingerprints" not in columns:
                    conn.execute(text("ALTER TABLE import_jobs ADD COLUMN excluded_row_fingerprints TEXT"))
                    logger.info("Migrated: Added import_jobs.excluded_row_fingerprints.")
        if inspector.has_table("accounts"):
            columns = [col["name"] for col in inspector.get_columns("accounts")]
            with engine.begin() as conn:
                if "last_reconciled_at" not in columns:
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN last_reconciled_at TIMESTAMP"))
                    logger.info("Migrated: Added accounts.last_reconciled_at.")
                if "last_reconciled_balance" not in columns:
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN last_reconciled_balance NUMERIC(14,2)"))
                    logger.info("Migrated: Added accounts.last_reconciled_balance.")
                if "reconciliation_note" not in columns:
                    conn.execute(text("ALTER TABLE accounts ADD COLUMN reconciliation_note TEXT"))
                    logger.info("Migrated: Added accounts.reconciliation_note.")
        if inspector.has_table("transactions"):
            columns = [col["name"] for col in inspector.get_columns("transactions")]
            if "status" not in columns:
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN status VARCHAR(16) NOT NULL DEFAULT 'posted'"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_status ON transactions (status)"))
                    logger.info("Migrated: Added transactions.status.")
    except Exception as e:
        logger.warning("Failed to auto-migrate schema: %s", e)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Ledger API", version="1.4.0", docs_url="/docs")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_import_recovery_task: asyncio.Task | None = None


@app.on_event("startup")
async def start_import_recovery() -> None:
    """Start the lightweight database-backed import worker."""
    global _import_recovery_task
    _import_recovery_task = asyncio.create_task(_import_recovery_loop())


@app.on_event("shutdown")
async def stop_import_recovery() -> None:
    global _import_recovery_task
    if _import_recovery_task:
        _import_recovery_task.cancel()
        try:
            await _import_recovery_task
        except asyncio.CancelledError:
            pass
        _import_recovery_task = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _month_range(month: str) -> tuple[date, date]:
    start = date.fromisoformat(f"{month}-01")
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def _tx_query(db: Session, user_id: str, month: str | None = None, *, include_unposted: bool = False):
    q = db.query(Transaction).filter(Transaction.user_id == user_id)
    if not include_unposted:
        q = q.filter(Transaction.status == "posted")
    if month:
        start, end = _month_range(month)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    return q.order_by(Transaction.date.desc(), Transaction.created_at.desc())


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _statement_row_fingerprint(row: dict, account_id: str | None = None) -> str:
    """Stable row identity that preserves legitimate same-value transactions across accounts."""
    row_date = row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"])
    description = " ".join(str(row.get("description", "")).casefold().split())
    raw = f"statement:v2|{account_id or 'unassigned'}|{row_date}|{row.get('type', 'expense')}|{row['amount']}|{description}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _merchant_key(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _resolve_merchant_alias(db: Session, user_id: str, description: str, proposed: str | None = None) -> str | None:
    """Apply a user alias while retaining the original statement description."""
    candidates = {_merchant_key(description)}
    if proposed:
        candidates.add(_merchant_key(proposed))
    alias = (
        db.query(MerchantAlias)
        .filter(MerchantAlias.user_id == user_id, MerchantAlias.alias_key.in_(candidates))
        .order_by(MerchantAlias.created_at.desc())
        .first()
    )
    return alias.canonical if alias else proposed


def _recurring_payload(rule: RecurringRule) -> dict:
    return {
        "id": rule.id,
        "description": rule.description,
        "category": rule.category,
        "cadence": rule.cadence,
        "average_amount": rule.average_amount,
        "minimum_amount": rule.minimum_amount,
        "maximum_amount": rule.maximum_amount,
        "next_expected": rule.next_expected,
        "confidence": rule.confidence,
        "status": rule.status,
        "confirmed": rule.confirmed,
        "evidence_transaction_ids": json.loads(rule.evidence_transaction_ids or "[]"),
        "confirmed_at": rule.confirmed_at,
        "created_at": rule.created_at,
        "updated_at": rule.updated_at,
    }


def _get_balance_at(
    db: Session,
    user_id: str,
    as_of_date: date | None = None,
    exclude_id: str | None = None,
) -> Decimal | None:
    """
    Returns the true running balance for a user as of (but NOT including)
    `as_of_date`. If `as_of_date` is None, returns the current balance.

    Strategy (pure SQL, no Python ordering tricks):
    1. Find the LAST transaction that has a bank-reported running_balance,
       ordered strictly by (date DESC, created_at DESC, stmt_seq DESC NULLS LAST).
       This is our "anchor" — the most recently known authoritative balance.
    2. Sum all transactions that came in STRICTLY AFTER the anchor row
       (same ordering criteria, using anchors values as the inequality boundary)
       to compute the net_change since that anchor.
    3. Return anchor.running_balance + net_change.
    """
    from sqlalchemy import and_, case, func, or_

    # ── Step 1: find the anchor row ──
    anchor_q = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.status == "posted",
        Transaction.running_balance.isnot(None),
        Transaction.source != "cash",
    )
    if as_of_date:
        anchor_q = anchor_q.filter(Transaction.date < as_of_date)
    if exclude_id:
        anchor_q = anchor_q.filter(Transaction.id != exclude_id)

    anchor = anchor_q.order_by(
        Transaction.date.desc(),
        Transaction.created_at.desc(),
        Transaction.stmt_seq.desc().nulls_last(),
    ).first()

    if anchor is None:
        return None

    # ── Step 2: sum all transactions AFTER the anchor ──
    # "after" means: date > anchor.date
    #              OR (date == anchor.date AND created_at > anchor.created_at)
    #              OR (date == anchor.date AND created_at == anchor.created_at
    #                  AND COALESCE(stmt_seq, MAX_INT) > COALESCE(anchor.stmt_seq, MAX_INT))
    anchor_seq = anchor.stmt_seq if anchor.stmt_seq is not None else 2_147_483_647

    after_filter = or_(
        Transaction.date > anchor.date,
        and_(
            Transaction.date == anchor.date,
            Transaction.created_at > anchor.created_at,
        ),
        and_(
            Transaction.date == anchor.date,
            Transaction.created_at == anchor.created_at,
            func.coalesce(Transaction.stmt_seq, 2147483647) > anchor_seq,
        ),
    )

    # Single SQL aggregate (income + refund - expense) instead of pulling every row into
    # Python and summing. Avoids O(n²) work when this is called per-row during
    # statement import, and keeps memory flat regardless of history size.
    signed_amount = case(
        (Transaction.type.in_(("income", "refund", "reimbursement")), Transaction.amount),
        (Transaction.type == "expense", -Transaction.amount),
        else_=0,
    )
    net_q = db.query(func.coalesce(func.sum(signed_amount), 0)).filter(
        Transaction.user_id == user_id,
        Transaction.status == "posted",
        Transaction.id != anchor.id,
        Transaction.source != "cash",
        after_filter,
    )
    if as_of_date:
        net_q = net_q.filter(Transaction.date < as_of_date)
    if exclude_id:
        net_q = net_q.filter(Transaction.id != exclude_id)

    net_change = Decimal(str(net_q.scalar() or 0))

    return anchor.running_balance + net_change


def _history_start(range_key: str | None) -> date | None:
    from datetime import date as dt_date
    from datetime import timedelta

    today = dt_date.today()
    if range_key in ("this_month", "30d"):
        return today - timedelta(days=30)
    if range_key == "current_year":
        return today.replace(month=1, day=1)
    if not range_key or range_key == "3m":
        return today - timedelta(days=92)
    if range_key == "1y":
        return today - timedelta(days=365)
    if range_key == "all":
        return None
    raise HTTPException(status_code=400, detail="range must be this_month, 3m, current_year, 1y, or all")


def _cursor_encode(tx: Transaction) -> str:
    return base64.urlsafe_b64encode(f"{tx.date}|{tx.id}".encode()).decode()


def _cursor_decode(cursor: str) -> tuple[date, str]:
    decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
    date_str, tx_id = decoded.split("|", 1)
    return date.fromisoformat(date_str), tx_id


def _wants_last_transaction(question: str) -> bool:
    text = question.lower()
    return "last transaction" in text or "latest transaction" in text or "most recent transaction" in text


def _wants_overspending(question: str) -> bool:
    text = question.lower()
    return "overspending" in text or "spending most" in text or "spent most" in text or "most spend" in text


def _format_transaction(tx: Transaction) -> str:
    direction = {"income": "income", "expense": "expense", "refund": "refund", "transfer": "transfer"}.get(tx.type, tx.type)
    return (
        f"Your latest transaction is {direction} of INR {tx.amount} on {tx.date.isoformat()} "
        f"for {tx.description} in {tx.category}."
    )


def _format_overspending(transactions: list[Transaction]) -> str:
    from collections import defaultdict

    totals = defaultdict(lambda: {"amount": 0, "count": 0})
    dates = [tx.date for tx in transactions]
    for tx in transactions:
        if tx.type != "expense":
            continue
        totals[tx.category]["amount"] += float(tx.amount)
        totals[tx.category]["count"] += 1
    if not totals:
        return "No expense transactions were found for this signed-in account."
    ranked = sorted(totals.items(), key=lambda item: item[1]["amount"], reverse=True)
    top = ranked[0]
    runners = ", ".join(f"{cat}: INR {data['amount']:.0f}" for cat, data in ranked[1:4])
    extra = f" Next highest: {runners}." if runners else ""
    period = f" from {min(dates).isoformat()} to {max(dates).isoformat()}" if dates else ""
    return (
        f"You are spending most{period} in {top[0]}: INR {top[1]['amount']:.0f} "
        f"across {top[1]['count']} transactions.{extra}"
    )


def _transaction_snapshot(tx: Transaction) -> dict:
    """Serialize the editable transaction fields for an auditable one-step undo."""
    return {
        "date": tx.date.isoformat(),
        "type": tx.type,
        "status": getattr(tx, "status", "posted"),
        "category": tx.category,
        "amount": str(tx.amount),
        "description": tx.description,
        "merchant_normalized": tx.merchant_normalized,
        "confidence": tx.confidence,
        "source": tx.source,
        "source_ref": tx.source_ref,
        "account_id": tx.account_id,
        "tags": tx.tags,
        "notes": tx.notes,
        "running_balance": str(tx.running_balance) if tx.running_balance is not None else None,
        "stmt_seq": tx.stmt_seq,
    }


# ── Keep-alive ping (Render free tier cold-start prevention) ─────────────────
@app.get("/ping")
def ping():
    """Lightweight health check / keep-alive. No DB, no auth. ~0ms overhead."""
    return {"pong": True}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "version": "1.4.0"}


# ── Profile ───────────────────────────────────────────────────────────────────
@app.get("/profile", response_model=UserProfileOut)
def get_profile(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@app.put("/profile", response_model=UserProfileOut)
def update_profile(
    payload: UserProfileIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.display_name is not None:
        db_user.display_name = payload.display_name.strip() or None
    if payload.avatar_url is not None:
        db_user.avatar_url = payload.avatar_url
    db_user.currency_preference = payload.currency_preference
    db.commit()
    db.refresh(db_user)
    logger.info("profile.updated user=%s", user.id)
    return db_user


@app.get("/profile/stats", response_model=ProfileStatsOut)
def get_profile_stats(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    # SQLite-compatible separate aggregate queries
    total_txns = db.query(func.count(Transaction.id)).filter(Transaction.user_id == user.id).scalar() or 0
    total_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user.id, Transaction.status == "posted", Transaction.type == "income"
    ).scalar() or Decimal("0")
    signed_expense = case(
        (Transaction.type == "expense", Transaction.amount),
        (Transaction.type.in_(("refund", "reimbursement")), -Transaction.amount),
        else_=0,
    )
    total_expenses = db.query(func.coalesce(func.sum(signed_expense), 0)).filter(
        Transaction.user_id == user.id, Transaction.status == "posted", Transaction.type.in_(("expense", "refund", "reimbursement"))
    ).scalar() or Decimal("0")
    accounts_count = (
        db.query(func.count(Account.id)).filter(Account.user_id == user.id, Account.is_active.is_(True)).scalar() or 0
    )
    budgets_count = db.query(func.count(Budget.id)).filter(Budget.user_id == user.id).scalar() or 0

    return ProfileStatsOut(
        total_transactions=total_txns,
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=total_income - total_expenses,
        accounts_count=accounts_count,
        budgets_count=budgets_count,
    )


# ── Personalization ─────────────────────────────────────────────────────────
@app.get("/merchant-aliases", response_model=list[MerchantAliasOut])
def list_merchant_aliases(user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id).order_by(MerchantAlias.alias_key).all()


@app.post("/merchant-aliases", response_model=MerchantAliasOut, status_code=201)
def upsert_merchant_alias(
    payload: MerchantAliasIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alias_key = _merchant_key(payload.alias)
    canonical = " ".join(payload.canonical.strip().split())
    if not alias_key or _merchant_key(canonical) == alias_key:
        raise HTTPException(status_code=400, detail="Alias and canonical merchant must be different")
    alias = db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id, MerchantAlias.alias_key == alias_key).first()
    action = "update" if alias else "create"
    if alias:
        alias.canonical = canonical
    else:
        alias = MerchantAlias(user_id=user.id, alias_key=alias_key, canonical=canonical)
        db.add(alias)
    matching = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    applied = 0
    for tx in matching:
        if _merchant_key(tx.description) == alias_key or _merchant_key(tx.merchant_normalized) == alias_key:
            tx.merchant_normalized = canonical
            applied += 1
    db.flush()
    log_event(db, user_id=user.id, action=action, resource_type="merchant_alias", resource_id=alias.id,
              details={"applied_transaction_count": applied}, ip_address=_client_ip(request))
    db.commit()
    db.refresh(alias)
    return alias


@app.delete("/merchant-aliases/{alias_id}")
def delete_merchant_alias(
    alias_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    alias = db.get(MerchantAlias, alias_id)
    if not alias or alias.user_id != user.id:
        raise HTTPException(status_code=404, detail="Merchant alias not found")
    db.delete(alias)
    log_event(db, user_id=user.id, action="delete", resource_type="merchant_alias", resource_id=alias_id,
              ip_address=_client_ip(request))
    db.commit()
    return {"deleted": True}


def _category_payload(name: str, kind: str, reporting_group: str, *, is_custom: bool, category_id: str) -> dict:
    return {"id": category_id, "name": name, "kind": kind, "reporting_group": reporting_group,
            "is_active": True, "is_custom": is_custom}


@app.get("/categories", response_model=list[UserCategoryOut])
def list_categories(user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    builtins = [
        _category_payload(name, "income" if name in {"Salary", "Freelance"} else "expense", name,
                          is_custom=False, category_id=f"default:{name}")
        for name in CATEGORIES
    ]
    custom = db.query(UserCategory).filter(UserCategory.user_id == user.id, UserCategory.is_active.is_(True)).order_by(UserCategory.name).all()
    return builtins + [_category_payload(c.name, c.kind, c.reporting_group, is_custom=True, category_id=c.id) for c in custom]


@app.post("/categories", response_model=UserCategoryOut, status_code=201)
def create_category(
    payload: UserCategoryIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    name = " ".join(payload.name.strip().split())
    if name.casefold() in {value.casefold() for value in CATEGORIES}:
        raise HTTPException(status_code=409, detail="That category is already built in")
    existing = db.query(UserCategory).filter(UserCategory.user_id == user.id, UserCategory.name.ilike(name), UserCategory.kind == payload.kind).first()
    if existing:
        if not existing.is_active:
            existing.is_active = True
            existing.reporting_group = payload.reporting_group
        else:
            raise HTTPException(status_code=409, detail="That category already exists")
        category = existing
    else:
        category = UserCategory(user_id=user.id, name=name, kind=payload.kind, reporting_group=payload.reporting_group)
        db.add(category)
    db.flush()
    log_event(db, user_id=user.id, action="create", resource_type="category", resource_id=category.id, ip_address=_client_ip(request))
    db.commit()
    return _category_payload(category.name, category.kind, category.reporting_group, is_custom=True, category_id=category.id)


@app.delete("/categories/{category_id}")
def deactivate_category(
    category_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    category = db.get(UserCategory, category_id)
    if not category or category.user_id != user.id:
        raise HTTPException(status_code=404, detail="Custom category not found")
    category.is_active = False
    log_event(db, user_id=user.id, action="deactivate", resource_type="category", resource_id=category.id, ip_address=_client_ip(request))
    db.commit()
    return {"deleted": True}


@app.get("/recurring", response_model=list[RecurringRuleOut])
def list_recurring_rules(user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = db.query(RecurringRule).filter(RecurringRule.user_id == user.id).order_by(RecurringRule.status, RecurringRule.next_expected).all()
    return [_recurring_payload(rule) for rule in rules]


def _validated_evidence_ids(db: Session, user_id: str, ids: list[str]) -> list[str]:
    if not ids:
        return []
    rows = db.query(Transaction.id).filter(Transaction.user_id == user_id, Transaction.id.in_(ids), Transaction.status == "posted").all()
    valid = {row[0] for row in rows}
    invalid = [value for value in ids if value not in valid]
    if invalid:
        raise HTTPException(status_code=400, detail="Recurring evidence must reference posted transactions owned by this user")
    return list(dict.fromkeys(ids))


@app.post("/recurring", response_model=RecurringRuleOut, status_code=201)
def create_recurring_rule(
    payload: RecurringRuleIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    values = payload.model_dump()
    evidence = _validated_evidence_ids(db, user.id, values.pop("evidence_transaction_ids"))
    confirmed = values.get("confirmed", False)
    rule = RecurringRule(user_id=user.id, **values, evidence_transaction_ids=json.dumps(evidence), confirmed_at=datetime.now(UTC) if confirmed else None)
    db.add(rule)
    db.flush()
    log_event(db, user_id=user.id, action="create", resource_type="recurring_rule", resource_id=rule.id, ip_address=_client_ip(request))
    db.commit()
    db.refresh(rule)
    return _recurring_payload(rule)


@app.put("/recurring/{rule_id}", response_model=RecurringRuleOut)
def update_recurring_rule(
    rule_id: str,
    payload: RecurringRuleIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.get(RecurringRule, rule_id)
    if not rule or rule.user_id != user.id:
        raise HTTPException(status_code=404, detail="Recurring rule not found")
    values = payload.model_dump()
    evidence = _validated_evidence_ids(db, user.id, values.pop("evidence_transaction_ids"))
    for key, value in values.items():
        if key != "confirmed":
            setattr(rule, key, value)
    rule.confirmed = values["confirmed"]
    rule.evidence_transaction_ids = json.dumps(evidence)
    if rule.confirmed and not rule.confirmed_at:
        rule.confirmed_at = datetime.now(UTC)
    if not rule.confirmed:
        rule.confirmed_at = None
    log_event(db, user_id=user.id, action="update", resource_type="recurring_rule", resource_id=rule.id, ip_address=_client_ip(request))
    db.commit()
    db.refresh(rule)
    return _recurring_payload(rule)


@app.delete("/recurring/{rule_id}")
def delete_recurring_rule(
    rule_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rule = db.get(RecurringRule, rule_id)
    if not rule or rule.user_id != user.id:
        raise HTTPException(status_code=404, detail="Recurring rule not found")
    db.delete(rule)
    log_event(db, user_id=user.id, action="delete", resource_type="recurring_rule", resource_id=rule_id, ip_address=_client_ip(request))
    db.commit()
    return {"deleted": True}


# ── Transactions ──────────────────────────────────────────────────────────────
@app.get("/transactions", response_model=PaginatedTransactions)
def list_transactions(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    month: str | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    tx_type: str | None = Query(None, alias="type"),
    tx_status: str | None = Query(None, alias="status", pattern="^(posted|pending|excluded)$"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id)

    if month:
        start, end = _month_range(month)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    if category:
        q = q.filter(Transaction.category == category)
    if tx_type and tx_type in ("income", "expense", "refund", "reimbursement", "transfer"):
        q = q.filter(Transaction.type == tx_type)
    if tx_status:
        q = q.filter(Transaction.status == tx_status)
    else:
        q = q.filter(Transaction.status == "posted")
    if search:
        pattern = f"%{search.lower()}%"
        q = q.filter(Transaction.description.ilike(pattern))
    if cursor:
        try:
            cursor_date, cursor_id = _cursor_decode(cursor)
            q = q.filter(
                (Transaction.date < cursor_date) | ((Transaction.date == cursor_date) & (Transaction.id < cursor_id))
            )
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid cursor")

    q = q.order_by(Transaction.date.desc(), Transaction.id.desc())
    rows = q.limit(limit + 1).all()
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = _cursor_encode(items[-1]) if has_more and items else None

    return PaginatedTransactions(
        items=items,
        next_cursor=next_cursor,
        has_more=has_more,
        total_returned=len(items),
    )


@app.post("/transactions", response_model=TransactionOut, status_code=201)
def create_transaction(
    payload: TransactionIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")
    tx = Transaction(user_id=user.id, **payload.model_dump())
    tx.merchant_normalized = _resolve_merchant_alias(db, user.id, tx.description, tx.merchant_normalized)
    db.add(tx)
    db.flush()  # assign tx.id before backfill query

    # Backfill running_balance so the DB is always the source of truth.
    # running_balance = (last known balance) ± this transaction's amount.
    if tx.running_balance is None and tx.source != "cash":
        prior_balance = _get_balance_at(db, user.id, as_of_date=None, exclude_id=tx.id)
        if prior_balance is not None:
            if tx.type in ("income", "refund", "reimbursement") and tx.status == "posted":
                tx.running_balance = prior_balance + tx.amount
            elif tx.type == "expense" and tx.status == "posted":
                tx.running_balance = prior_balance - tx.amount

    db.commit()
    db.refresh(tx)
    logger.info("transaction.created user=%s id=%s amount=%s balance=%s", user.id, tx.id, tx.amount, tx.running_balance)
    return tx


@app.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    log_event(
        db, user_id=user.id, action="delete", resource_type="transaction",
        resource_id=transaction_id, ip_address=_client_ip(request),
    )
    db.commit()
    logger.info("transaction.deleted user=%s id=%s", user.id, transaction_id)
    return {"deleted": True}


@app.post("/transactions/bulk-delete")
def bulk_delete_transactions(
    payload: BulkDeleteRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.id.in_(payload.transaction_ids),
            Transaction.user_id == user.id,
        )
        .all()
    )
    if not txs:
        return {"deleted_count": 0}

    count = len(txs)
    for tx in txs:
        db.delete(tx)
    log_event(
        db, user_id=user.id, action="delete", resource_type="transaction",
        details={"bulk": True, "count": count}, ip_address=_client_ip(request),
    )
    db.commit()
    logger.info("transactions.bulk_deleted user=%s count=%d", user.id, count)
    return {"deleted_count": count}


# ── Budgets ───────────────────────────────────────────────────────────────────
@app.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Budget).filter(Budget.user_id == user.id).order_by(Budget.category).all()


# ── Goals ────────────────────────────────────────────────────────────────────
@app.get("/goals", response_model=list[GoalOut])
def list_goals(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.status, Goal.deadline, Goal.created_at).all()


@app.post("/goals", response_model=GoalOut, status_code=201)
def create_goal(
    payload: GoalIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    values = payload.model_dump()
    if values["current_amount"] >= values["target_amount"] and values["status"] == "active":
        values["status"] = "completed"
    goal = Goal(user_id=user.id, **values)
    db.add(goal)
    db.flush()
    log_event(db, user_id=user.id, action="create", resource_type="goal", resource_id=goal.id, ip_address=_client_ip(request))
    db.commit()
    db.refresh(goal)
    return goal


@app.put("/goals/{goal_id}", response_model=GoalOut)
def update_goal(
    goal_id: str,
    payload: GoalIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found")
    values = payload.model_dump()
    if values["current_amount"] >= values["target_amount"] and values["status"] == "active":
        values["status"] = "completed"
    for key, value in values.items():
        setattr(goal, key, value)
    log_event(db, user_id=user.id, action="update", resource_type="goal", resource_id=goal.id, ip_address=_client_ip(request))
    db.commit()
    db.refresh(goal)
    return goal


@app.delete("/goals/{goal_id}")
def delete_goal(
    goal_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.get(Goal, goal_id)
    if not goal or goal.user_id != user.id:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    log_event(db, user_id=user.id, action="delete", resource_type="goal", resource_id=goal.id, ip_address=_client_ip(request))
    db.commit()
    return {"deleted": True}


@app.put("/budgets", response_model=list[BudgetOut])
def upsert_budgets(
    payload: list[BudgetIn],
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing = {b.category: b for b in db.query(Budget).filter(Budget.user_id == user.id).all()}
    saved = []
    for item in payload:
        budget = existing.get(item.category)
        if budget:
            budget.monthly_limit = item.monthly_limit
            budget.strategy = item.strategy
        else:
            budget = Budget(user_id=user.id, **item.model_dump())
            db.add(budget)
        saved.append(budget)
    log_event(
        db, user_id=user.id, action="update", resource_type="budget",
        details={"categories": [item.category for item in payload]},
        ip_address=_client_ip(request),
    )
    db.commit()
    for b in saved:
        db.refresh(b)
    return saved


@app.get("/budgets/suggestions")
def budget_suggestions(
    range: str | None = Query("3m", pattern="^(3m|1y|all)$"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.status == "posted", Transaction.type == "expense")
    start = _history_start(range)
    if start:
        q = q.filter(Transaction.date >= start)
    txs = q.all()
    return dynamic_budget_suggestions(txs)


# ── Summary ───────────────────────────────────────────────────────────────────
@app.get("/summary")
def get_summary(
    month: str | None = None,
    range: str | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = _tx_query(db, user.id, month)
    if not month and range:
        start = _history_start(range)
        if start:
            q = q.filter(Transaction.date >= start)
    transactions = q.all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    summary = monthly_summary(transactions)
    quality = data_quality(transactions)
    quality.update(
        {
            "unassigned_account_count": db.query(Transaction.id).filter(
                Transaction.user_id == user.id,
                Transaction.source != "cash",
                Transaction.account_id.is_(None),
            ).count(),
            "active_accounts": db.query(Account.id).filter(
                Account.user_id == user.id, Account.is_active.is_(True)
            ).count(),
            "reconciled_accounts": db.query(Account.id).filter(
                Account.user_id == user.id,
                Account.is_active.is_(True),
                Account.last_reconciled_at.isnot(None),
            ).count(),
            "pending_imports": db.query(ImportJob.id).filter(
                ImportJob.user_id == user.id, ImportJob.status.in_(("pending", "processing"))
            ).count(),
            "failed_imports": db.query(ImportJob.id).filter(
                ImportJob.user_id == user.id, ImportJob.status == "failed"
            ).count(),
            "pending_transactions": db.query(Transaction.id).filter(
                Transaction.user_id == user.id, Transaction.status == "pending"
            ).count(),
            "excluded_transactions": db.query(Transaction.id).filter(
                Transaction.user_id == user.id, Transaction.status == "excluded"
            ).count(),
        }
    )
    quality["stale_account_count"] = max(0, quality["active_accounts"] - quality["reconciled_accounts"])
    quality["account_balance_quality"] = (
        "none" if quality["active_accounts"] == 0 else
        "reconciled" if quality["stale_account_count"] == 0 else
        "mixed_or_unreconciled"
    )
    if quality["unassigned_account_count"]:
        quality["warnings"].append("Assign imported transactions to an account for reliable balances")
    if quality["failed_imports"]:
        quality["warnings"].append("Review failed statement imports")
    if quality["pending_transactions"]:
        quality["warnings"].append("Review pending transactions before relying on committed totals")
    if quality["stale_account_count"]:
        quality["warnings"].append("Reconcile active account balances for a stronger balance picture")

    summary["closing_balance"] = _get_balance_at(db, user.id, as_of_date=None)
    summary["opening_balance"] = None
    if month:
        period_start_d, period_end = _month_range(month)
        summary["closing_balance"] = _get_balance_at(db, user.id, as_of_date=period_end)
        summary["opening_balance"] = _get_balance_at(db, user.id, as_of_date=period_start_d)
    elif range:
        period_start_d = _history_start(range)
        if period_start_d:
            summary["opening_balance"] = _get_balance_at(db, user.id, as_of_date=period_start_d)

    summary["analysis"] = build_analysis_object(transactions, summary, quality)
    summary["analysis"]["comparison"] = compare_periods(transactions, days=30)

    return {
        **summary,
        "insights": compute_insights(transactions, budgets),
        "recurring": recurring_payments(transactions),
        "data_quality": quality,
    }


# ── SMS Import ────────────────────────────────────────────────────────────────
@app.post("/imports/sms", response_model=list[TransactionOut])
@limiter.limit(settings.import_rate_limit)
async def import_sms(
    request: Request,
    payload: SmsParseRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = []
    pending_txs: list[Transaction] = []
    for message in payload.messages:
        parsed = parse_sms(message)
        if not parsed:
            continue
        duplicate = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.source == "sms",
                Transaction.source_ref == parsed["source_ref"],
            )
            .first()
        )
        if duplicate:
            continue
        tx = Transaction(user_id=user.id, **parsed)
        db.add(tx)
        pending_txs.append(tx)
    db.commit()

    # ── AI Categorization upgrade pass ────────────────────────────────────────
    # parse_sms uses keyword rules — upgrade with the full 4-tier pipeline.
    if pending_txs:
        try:
            db.flush()  # ensure tx.id is assigned before we reference it
            user_overrides = get_user_overrides(db, user.id)
            batch_input = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in pending_txs]
            ai_results = await categorize_batch(batch_input, user_overrides=user_overrides)
            ai_map = {r["id"]: r for r in ai_results}
            for tx in pending_txs:
                res = ai_map.get(tx.id)
                if res and res.get("confidence", 0) >= 0.6 and res.get("category", "Other") != "Other":
                    tx.category = res["category"]
                    tx.confidence = res["confidence"]
                if res and res.get("merchant"):
                    tx.merchant_normalized = res["merchant"]
            db.commit()
        except Exception as ai_err:
            logger.warning("SMS AI categorization pass failed: %s", ai_err)

    for tx in pending_txs:
        db.refresh(tx)
        saved.append(tx)
    logger.info("sms.import user=%s imported=%d", user.id, len(saved))
    return saved


@app.post("/imports/sms/webhook", response_model=list[TransactionOut])
async def import_sms_webhook(
    payload: SmsWebhookRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive SMS payloads from an Android companion bridge and reuse the SMS parser."""
    saved = []
    pending_txs: list[Transaction] = []
    for message in payload.messages:
        parsed = parse_sms(message)
        if not parsed:
            continue
        if payload.device_id:
            parsed["notes"] = f"SMS bridge device: {payload.device_id}"
        duplicate = (
            db.query(Transaction)
            .filter(
                Transaction.user_id == user.id,
                Transaction.source == "sms",
                Transaction.source_ref == parsed["source_ref"],
            )
            .first()
        )
        if duplicate:
            continue
        tx = Transaction(user_id=user.id, **parsed)
        db.add(tx)
        pending_txs.append(tx)
    db.commit()

    # ── AI Categorization upgrade pass ────────────────────────────────────────
    if pending_txs:
        try:
            user_overrides = get_user_overrides(db, user.id)
            batch_input = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in pending_txs]
            ai_results = await categorize_batch(batch_input, user_overrides=user_overrides)
            ai_map = {r["id"]: r for r in ai_results}
            for tx in pending_txs:
                res = ai_map.get(tx.id)
                if res and res.get("confidence", 0) >= 0.6 and res.get("category", "Other") != "Other":
                    tx.category = res["category"]
                    tx.confidence = res["confidence"]
                if res and res.get("merchant"):
                    tx.merchant_normalized = res["merchant"]
            db.commit()
        except Exception as ai_err:
            logger.warning("SMS webhook AI categorization pass failed: %s", ai_err)

    for tx in pending_txs:
        db.refresh(tx)
        saved.append(tx)
    logger.info("sms.webhook user=%s device=%s imported=%d", user.id, payload.device_id, len(saved))
    return saved


# ── Statement Import (async job) ──────────────────────────────────────────────
@app.post("/imports/statement/preview", response_model=ImportPreviewOut)
@limiter.limit(settings.import_rate_limit)
async def preview_statement_import(
    request: Request,
    file: UploadFile = File(...),
    account_id: str | None = Form(default=None),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse a statement without writing transactions so the user can review it."""
    started = time.perf_counter()
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = file.filename.lower().rsplit(".", 1)[-1]
    if ext not in ("csv", "pdf", "xls", "xlsx", "ods"):
        raise HTTPException(status_code=400, detail="Upload a CSV, Excel, OpenDocument, or PDF statement")
    if account_id:
        account = db.get(Account, account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.max_upload_mb}MB)")

    if ext == "csv":
        rows = parse_csv(content)
    elif ext in ("xls", "xlsx", "ods"):
        rows = parse_excel(content, ext)
    else:
        rows = await parse_pdf(content)

    if len(rows) > settings.max_import_rows:
        raise HTTPException(status_code=400, detail=f"Statement has more than {settings.max_import_rows} rows")

    fingerprints = [_statement_row_fingerprint(row, account_id) for row in rows]
    existing_refs = {
        ref for (ref,) in db.query(Transaction.source_ref).filter(
            Transaction.user_id == user.id,
            Transaction.source == "statement",
            Transaction.source_ref.in_(fingerprints or ["__none__"]),
        ).all()
    }
    seen: set[str] = set()
    duplicate_count = 0
    category_results = {}
    if rows:
        try:
            user_overrides = get_user_overrides(db, user.id)
            category_results = {
                str(result.get("id")): result
                for result in await categorize_batch(
                    [
                        {"id": str(index), "description": row["description"], "type": row.get("type", "expense")}
                        for index, row in enumerate(rows)
                    ],
                    user_overrides=user_overrides,
                )
            }
        except Exception as ai_err:
            logger.warning("Statement preview AI categorization failed: %s", ai_err)
    preview_rows = []
    for index, (row, fingerprint) in enumerate(zip(rows, fingerprints, strict=True)):
        duplicate = fingerprint in existing_refs or fingerprint in seen
        if duplicate:
            duplicate_count += 1
        seen.add(fingerprint)
        category_result = category_results.get(str(index), {})
        preview_rows.append({
            "fingerprint": fingerprint,
            "date": row["date"],
            "type": row["type"],
            "amount": row["amount"],
            "description": row["description"],
            "category": category_result.get("category") or row.get("category", "Other"),
            "category_confidence": category_result.get("confidence"),
            "merchant_normalized": category_result.get("merchant"),
            "duplicate": duplicate,
        })

    warnings = []
    if not rows:
        warnings.append("No transactions could be extracted from this file")
    if duplicate_count:
        warnings.append(f"{duplicate_count} row(s) already exist or repeat within this file and will be skipped")
    if not account_id:
        warnings.append("No account selected; imported rows will not contribute to an account balance")
    if ext == "pdf" and rows:
        warnings.append("PDF imports use parsed text; review dates, amounts, and debit/credit direction before confirming")

    result = {
        "file_name": file.filename,
        "row_count": len(rows),
        "duplicate_count": duplicate_count,
        "preview": preview_rows[:100],
        "warnings": warnings,
    }
    record_telemetry(
        "import.preview",
        user_id=user.id,
        latency_ms=(time.perf_counter() - started) * 1000,
        parse_success=bool(rows),
        metadata={"count": len(rows), "warning_count": len(warnings)},
    )
    return result


async def _process_import_job(job_id: str) -> None:
    """Process one stored import job using a fresh session.

    Keeping the payload and processing metadata in the database means a worker
    restart can recover a job instead of losing the request closure.
    """
    worker_db = SessionLocal()
    worker_job = None
    try:
        claimed = worker_db.query(ImportJob).filter(
            ImportJob.id == job_id,
            ImportJob.status == "pending",
        ).update({ImportJob.status: "processing"}, synchronize_session=False)
        worker_db.commit()
        if not claimed:
            return
        worker_job = worker_db.get(ImportJob, job_id)
        if not worker_job:
            logger.error("import.worker_missing_job job=%s", job_id)
            return
        if not worker_job.file_content:
            worker_job.status = "failed"
            worker_job.error_message = "Import payload is unavailable; please upload the statement again."
            worker_db.commit()
            logger.error("import.worker_missing_payload job=%s", job_id)
            return
        if worker_job.status == "done":
            return
        worker_job.status = "processing"
        worker_db.commit()

        content = worker_job.file_content
        ext = worker_job.file_extension
        user_id = worker_job.user_id
        account_id = worker_job.account_id
        try:
            excluded_fingerprints = set(json.loads(worker_job.excluded_row_fingerprints or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            excluded_fingerprints = set()
        if ext == "csv":
            rows = parse_csv(content)
        elif ext in ("xls", "xlsx", "ods"):
            rows = parse_excel(content, ext)
        else:
            rows = await parse_pdf(content)

        if len(rows) > settings.max_import_rows:
            worker_job.status = "failed"
            worker_job.error_message = (
                f"Statement has {len(rows)} rows, over the {settings.max_import_rows}-row limit. "
                "Split the file and re-upload."
            )
            worker_db.commit()
            return

        worker_job.total_rows = len(rows)
        worker_job.processed_rows = 0
        worker_db.commit()
        if worker_job.cancel_requested:
            worker_job.status = "cancelled"
            worker_job.error_message = "Import cancelled before transactions were saved."
            worker_db.commit()
            return

        if rows:
            user_overrides = get_user_overrides(worker_db, user_id)
            batch_input = [
                {"id": str(i), "description": r["description"], "type": r.get("type", "expense")}
                for i, r in enumerate(rows)
            ]
            try:
                ai_results = await categorize_batch(batch_input, user_overrides=user_overrides)
                for res in ai_results:
                    idx = int(res["id"])
                    if res.get("confidence", 0) >= 0.6 and res.get("category", "Other") != "Other":
                        rows[idx]["category"] = res["category"]
                        rows[idx]["ai_confidence"] = res["confidence"]
                    if res.get("merchant"):
                        rows[idx]["merchant_normalized"] = res["merchant"]
            except Exception as ai_err:
                logger.warning("Statement AI categorization pass failed: %s", ai_err)

        prepared = []
        for seq, row in enumerate(rows):
            row["stmt_seq"] = seq
            merchant_norm = row.pop("merchant_normalized", None)
            ai_confidence = row.pop("ai_confidence", None)
            validated = TransactionIn(**row).model_dump()
            if account_id:
                validated["account_id"] = account_id
            fingerprint = _statement_row_fingerprint(validated, account_id)
            validated["source_ref"] = fingerprint
            prepared.append((validated, merchant_norm, ai_confidence, fingerprint))

        existing_refs: set[str] = set()
        if prepared:
            fingerprints = [fp for _, _, _, fp in prepared]
            existing_refs = {
                ref for (ref,) in worker_db.query(Transaction.source_ref).filter(
                    Transaction.user_id == user_id,
                    Transaction.source == "statement",
                    Transaction.source_ref.in_(fingerprints),
                ).all()
            }

        prior_bal = _get_balance_at(worker_db, user_id, as_of_date=None)
        saved_count = 0
        seen: set[str] = set()
        pending = 0
        for validated, merchant_norm, ai_confidence, fingerprint in prepared:
            cancel_requested = worker_db.query(ImportJob.cancel_requested).filter(ImportJob.id == job_id).scalar()
            if cancel_requested:
                worker_job.status = "cancelled"
                worker_job.cancel_requested = True
                worker_job.row_count = saved_count
                worker_job.processed_rows = min(worker_job.total_rows or 0, saved_count)
                worker_job.error_message = "Import cancelled; already processed rows remain safe and can be retried."
                worker_db.commit()
                return
            if fingerprint in existing_refs or fingerprint in seen:
                worker_job.processed_rows += 1
                continue
            if fingerprint in excluded_fingerprints:
                worker_job.processed_rows += 1
                continue
            seen.add(fingerprint)
            new_tx = Transaction(user_id=user_id, **validated)
            new_tx.merchant_normalized = _resolve_merchant_alias(worker_db, user_id, new_tx.description, merchant_norm)
            if ai_confidence is not None:
                new_tx.confidence = ai_confidence
            if new_tx.running_balance is None and new_tx.source != "cash" and prior_bal is not None:
                if new_tx.type in ("income", "refund", "reimbursement") and new_tx.status == "posted":
                    new_tx.running_balance = prior_bal + new_tx.amount
                elif new_tx.type == "expense" and new_tx.status == "posted":
                    new_tx.running_balance = prior_bal - new_tx.amount
            worker_db.add(new_tx)
            saved_count += 1
            pending += 1
            worker_job.processed_rows += 1
            if pending >= 100:
                worker_db.commit()
                pending = 0

        worker_job.status = "failed" if not rows else "done"
        worker_job.processed_rows = len(rows)
        worker_job.row_count = saved_count if rows else None
        if not rows:
            worker_job.error_message = (
                "No transactions could be extracted from this file. If this is a scanned/image PDF, "
                "export a digital PDF or CSV from your bank and re-upload."
            )
        else:
            worker_job.error_message = None
            worker_job.file_content = None
        worker_db.commit()
        record_telemetry(
            "import.completed",
            user_id=user_id,
            parse_success=bool(rows),
            outcome=worker_job.status,
            metadata={"count": saved_count, "status": worker_job.status},
        )
        logger.info("import.finished job=%s status=%s rows=%s", job_id, worker_job.status, saved_count)
    except Exception as exc:
        worker_db.rollback()
        worker_job = worker_db.get(ImportJob, job_id)
        if worker_job:
            worker_job.status = "failed"
            worker_job.error_message = str(exc)[:500]
            worker_db.commit()
            record_telemetry(
                "import.completed",
                user_id=worker_job.user_id,
                parse_success=False,
                outcome="failed",
                metadata={"status": "failed"},
            )
        logger.exception("import.failed job=%s", job_id)
    finally:
        worker_db.close()


async def _import_recovery_loop() -> None:
    """Recover pending jobs after a process restart."""
    await asyncio.sleep(1)
    while True:
        recovery_db = SessionLocal()
        try:
            job = recovery_db.query(ImportJob).filter(
                ImportJob.status == "pending",
                ImportJob.file_content.isnot(None),
            ).order_by(ImportJob.created_at).first()
            if not job:
                stale_before = datetime.now(UTC) - timedelta(minutes=5)
                job = recovery_db.query(ImportJob).filter(
                    ImportJob.status == "processing",
                    ImportJob.updated_at < stale_before,
                    ImportJob.file_content.isnot(None),
                ).order_by(ImportJob.updated_at).first()
                if job:
                    job.status = "pending"
                    recovery_db.commit()
            if job:
                job_id = job.id
            else:
                job_id = None
        except Exception:
            recovery_db.rollback()
            logger.exception("import.recovery.poll_failed")
            job_id = None
        finally:
            recovery_db.close()
        if job_id:
            await _process_import_job(job_id)
        else:
            await asyncio.sleep(5)


@app.post("/imports/statement", response_model=ImportJobOut, status_code=202)
@limiter.limit(settings.import_rate_limit)
async def import_statement(
    request: Request,
    file: UploadFile = File(...),
    account_id: str | None = Form(default=None),
    excluded_row_fingerprints: str | None = Form(default=None),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = file.filename.lower().rsplit(".", 1)[-1]
    if ext not in ("csv", "pdf", "xls", "xlsx", "ods"):
        raise HTTPException(status_code=400, detail="Upload a CSV, Excel, OpenDocument, or PDF statement")
    max_bytes = settings.max_upload_mb * 1024 * 1024
    # Fast-path reject when the client advertises a size; re-checked authoritatively
    # below since UploadFile.size is often None.
    if file.size and file.size > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.max_upload_mb}MB)")
    if account_id:
        account = db.get(Account, account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")

    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.max_upload_mb}MB)")

    file_fingerprint = hashlib.sha256(content).hexdigest()
    excluded_fingerprints: list[str] = []
    if excluded_row_fingerprints:
        try:
            parsed_exclusions = json.loads(excluded_row_fingerprints)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid excluded import rows") from exc
        if not isinstance(parsed_exclusions, list) or not all(isinstance(item, str) for item in parsed_exclusions):
            raise HTTPException(status_code=400, detail="Invalid excluded import rows")
        excluded_fingerprints = sorted(set(parsed_exclusions))[: settings.max_import_rows]
    existing_job = (
        db.query(ImportJob)
        .filter(
            ImportJob.user_id == user.id,
            ImportJob.account_id == account_id,
            ImportJob.file_fingerprint == file_fingerprint,
        )
        .order_by(ImportJob.created_at.desc())
        .first()
    )
    if existing_job:
        logger.info("import.idempotent_reupload user=%s job=%s status=%s", user.id, existing_job.id, existing_job.status)
        return existing_job

    # Persist the payload before scheduling work so a process restart can
    # recover the import from the database.
    job = ImportJob(
        user_id=user.id,
        file_name=file.filename,
        file_extension=ext,
        file_fingerprint=file_fingerprint,
        account_id=account_id,
        file_content=content,
        processed_rows=0,
        cancel_requested=False,
        excluded_row_fingerprints=json.dumps(excluded_fingerprints),
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    asyncio.create_task(_process_import_job(job.id))
    logger.info("import.started user=%s job=%s file=%s", user.id, job.id, file.filename)
    return job


@app.get("/imports/jobs", response_model=list[ImportJobOut])
def list_import_jobs(
    limit: int = Query(20, ge=1, le=100),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List recent statement jobs so users can recover failed imports."""
    return (
        db.query(ImportJob)
        .filter(ImportJob.user_id == user.id)
        .order_by(ImportJob.created_at.desc())
        .limit(limit)
        .all()
    )


@app.get("/imports/jobs/{job_id}", response_model=ImportJobOut)
def get_import_job(
    job_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@app.post("/imports/jobs/{job_id}/retry", response_model=ImportJobOut)
@limiter.limit(settings.import_rate_limit)
def retry_import(
    request: Request,
    job_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Requeue a failed import while its stored payload is still available."""
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Import job not found")
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail="Only failed or cancelled imports can be retried")
    if not job.file_content:
        raise HTTPException(status_code=410, detail="Import payload has expired; upload the statement again")
    job.status = "pending"
    job.row_count = None
    job.processed_rows = 0
    job.cancel_requested = False
    job.error_message = None
    db.commit()
    db.refresh(job)
    asyncio.create_task(_process_import_job(job.id))
    return job


@app.post("/imports/jobs/{job_id}/cancel", response_model=ImportJobOut)
def cancel_import(
    job_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Request cancellation of a pending or processing import."""
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Import job not found")
    if job.status not in ("pending", "processing"):
        raise HTTPException(status_code=409, detail="Only pending or processing imports can be cancelled")
    job.cancel_requested = True
    if job.status == "pending":
        job.status = "cancelled"
        job.error_message = "Import cancelled before processing started."
    db.commit()
    db.refresh(job)
    return job


# ── AI Advisor (streaming) ────────────────────────────────────────────────────
@app.post("/advisor/stream")
@limiter.limit(settings.advisor_rate_limit)
async def advisor_stream(
    request: Request,
    payload: AdvisorRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    question = sanitize_user_input(payload.question)
    transactions = _tx_query(db, user.id).limit(500).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    advisor_quality = data_quality(transactions)
    advisor_meta = {
        "type": "meta",
        "answer_type": "ai",
        "cloud_ai_configured": bool(ai_router.configured_providers()),
        "configured_providers": ai_router.configured_providers(),
        "period_start": advisor_quality.get("period_start"),
        "period_end": advisor_quality.get("period_end"),
        "transaction_count": advisor_quality.get("transaction_count", len(transactions)),
        "coverage": advisor_quality.get("coverage", "none"),
        "warnings": advisor_quality.get("warnings", []),
    }

    fact_answer = deterministic_answer(question, transactions, budgets)
    if fact_answer:
        advisor_meta.update({k: v for k, v in fact_answer.items() if k != "answer"})

        async def deterministic_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(fact_answer['answer'])}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            deterministic_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if _wants_last_transaction(question):
        latest = transactions[0] if transactions else None
        answer = _format_transaction(latest) if latest else "No transactions were found for this signed-in account."

        async def last_tx_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(answer)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            last_tx_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if _wants_overspending(question):
        answer = _format_overspending(transactions)

        async def overspending_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            yield f"data: {json.dumps(answer)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            overspending_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # Enrich advisor context with anomalies + forecast
    anomalies = detect_anomalies(transactions)
    forecast = generate_forecast(transactions)
    context = build_advisor_context(transactions, budgets, anomalies=anomalies, forecast=forecast)

    # Load conversation history if continuing a thread
    history = []
    conversation = None
    if payload.conversation_id:
        conversation = (
            db.query(AIConversation)
            .filter(
                AIConversation.id == payload.conversation_id,
                AIConversation.user_id == user.id,
            )
            .first()
        )
        if conversation:
            history = [
                {"role": m.role, "content": m.content}
                for m in sorted(conversation.messages, key=lambda m: m.created_at)
            ]

    messages = build_safe_messages(SYSTEM_PROMPT, context, question, history)

    # Create or update conversation
    if not conversation:
        conversation = AIConversation(
            user_id=user.id,
            title=question[:80],
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    user_msg = AIMessage(conversation_id=conversation.id, role="user", content=question)
    db.add(user_msg)
    db.commit()

    # Hash the complete message context, scoped to the user. The user prefix is
    # required so TTLCache.invalidate_user (which matches on the "{user_id}:"
    # prefix) actually evicts these entries when the user corrects a category —
    # otherwise stale advice lingers. It also rules out cross-user cache hits.
    context_hash = hashlib.sha256(json.dumps(messages).encode()).hexdigest()
    cache_key = f"{user.id}:advisor:{context_hash}"
    cached_reply = llm_cache.get(cache_key)

    if cached_reply:
        logger.info("Cache hit for advisor stream.")

        async def cached_event_generator():
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            # Yield cached string fully — JSON-encoded so embedded newlines
            # (markdown bullet points, paragraphs) survive SSE line parsing.
            yield f"data: {json.dumps(cached_reply)}\n\n"

            assistant_msg = AIMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=cached_reply,
            )
            db.add(assistant_msg)
            db.commit()
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            cached_event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Conversation-Id": conversation.id,
            },
        )

    async def event_generator():
        full_reply = []
        try:
            yield f"data: {json.dumps(advisor_meta)}\n\n"
            async for token in ai_router.stream(SYSTEM_PROMPT, messages):
                full_reply.append(token)
                yield f"data: {json.dumps(token)}\n\n"
        except Exception as e:
            logger.exception("advisor.stream.error user=%s", user.id)
            yield f"data: [ERROR] {str(e)[:100]}\n\n"
        finally:
            # Persist assistant reply
            if full_reply:
                reply_text = "".join(full_reply)
                llm_cache.put(cache_key, reply_text)

                assistant_msg = AIMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=reply_text,
                )
                db.add(assistant_msg)
                db.commit()
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Conversation-Id": conversation.id,
        },
    )


# ── Conversations ─────────────────────────────────────────────────────────────
@app.get("/conversations", response_model=list[ConversationOut])
def list_conversations(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(AIConversation)
        .filter(AIConversation.user_id == user.id)
        .order_by(AIConversation.updated_at.desc())
        .limit(20)
        .all()
    )


@app.get("/conversations/{conv_id}/messages", response_model=list[MessageOut])
def get_conversation_messages(
    conv_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conv_id,
            AIConversation.user_id == user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return sorted(conv.messages, key=lambda m: m.created_at)


@app.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = (
        db.query(AIConversation)
        .filter(
            AIConversation.id == conv_id,
            AIConversation.user_id == user.id,
        )
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.delete(conv)
    db.commit()
    logger.info("conversation.deleted user=%s id=%s", user.id, conv_id)
    return {"deleted": True}


# ── Accounts (Multi-Account Support) ─────────────────────────────────────────
@app.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Account).filter(Account.user_id == user.id, Account.is_active).order_by(Account.name).all()


@app.post("/accounts", response_model=AccountOut, status_code=201)
def create_account(
    payload: AccountIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = Account(user_id=user.id, **payload.model_dump())
    db.add(acct)
    db.commit()
    db.refresh(acct)
    logger.info("account.created user=%s id=%s name=%s", user.id, acct.id, acct.name)
    return acct


@app.put("/accounts/{account_id}", response_model=AccountOut)
def update_account(
    account_id: str,
    payload: AccountIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    for k, v in payload.model_dump().items():
        setattr(acct, k, v)
    log_event(
        db, user_id=user.id, action="update", resource_type="account",
        resource_id=account_id, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(acct)
    return acct


@app.post("/accounts/{account_id}/reconcile", response_model=ReconciliationOut)
def reconcile_account(
    account_id: str,
    payload: ReconciliationRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a real-world balance check and make the account balance current."""
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id or not acct.is_active:
        raise HTTPException(status_code=404, detail="Account not found")

    previous_balance = Decimal(str(acct.balance or 0))
    observed_balance = payload.observed_balance
    reconciled_at = datetime.now(UTC)
    acct.balance = observed_balance
    acct.last_reconciled_at = reconciled_at
    acct.last_reconciled_balance = observed_balance
    acct.reconciliation_note = payload.note
    log_event(
        db, user_id=user.id, action="reconcile", resource_type="account",
        resource_id=account_id, details={
            "previous_balance": str(previous_balance),
            "observed_balance": str(observed_balance),
            "difference": str(observed_balance - previous_balance),
        }, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(acct)
    return {
        "account_id": acct.id,
        "previous_balance": previous_balance,
        "observed_balance": observed_balance,
        "difference": observed_balance - previous_balance,
        "reconciled_at": reconciled_at,
        "note": payload.note,
    }


@app.delete("/accounts/{account_id}")
def delete_account(
    account_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    acct.is_active = False  # soft delete
    log_event(
        db, user_id=user.id, action="delete", resource_type="account",
        resource_id=account_id, ip_address=_client_ip(request),
    )
    db.commit()
    logger.info("account.deleted user=%s id=%s", user.id, account_id)
    return {"deleted": True}


# ── Auto-categorize ──────────────────────────────────────────────────────────
@app.post("/categorize", response_model=CategorizeSingleResponse)
@limiter.limit(settings.categorize_rate_limit)
async def auto_categorize(
    request: Request,
    payload: CategorizeSingleRequest,
    user: UserContext = Depends(get_current_user),
):
    result = await categorize_single(payload.description, payload.tx_type)
    return result


@app.post("/categorize/batch")
@limiter.limit(settings.categorize_rate_limit)
async def auto_categorize_batch(
    request: Request,
    payload: CategorizeBatchRequest,
    user: UserContext = Depends(get_current_user),
):
    results = await categorize_batch(payload.transactions)
    return results


# ── Proactive Insights ───────────────────────────────────────────────────────
# Proactive insights moved to end of file (v2 with anomaly + forecast context)


# ── Receipt OCR ───────────────────────────────────────────────────────────────
@app.post("/receipts/scan")
@limiter.limit(settings.receipt_rate_limit)
async def scan_receipt(
    request: Request,
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    ext = file.filename.lower().rsplit(".", 1)[-1]
    if ext not in ("jpg", "jpeg", "png", "webp"):
        raise HTTPException(status_code=400, detail="Upload an image (jpg, png, webp)")
    if file.size and file.size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image too large (max 5MB)")

    content = await file.read()
    result = await parse_receipt_image(content)
    if not result:
        raise HTTPException(status_code=422, detail="Could not extract data from receipt")
    return result


# ── Transaction Update ────────────────────────────────────────────────────────
@app.put("/transactions/{transaction_id}", response_model=TransactionOut)
def update_transaction(
    transaction_id: str,
    payload: TransactionIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if payload.account_id:
        account = db.get(Account, payload.account_id)
        if not account or account.user_id != user.id or not account.is_active:
            raise HTTPException(status_code=400, detail="Account is not available for this user")
    before = _transaction_snapshot(tx)
    for k, v in payload.model_dump().items():
        setattr(tx, k, v)
    tx.merchant_normalized = _resolve_merchant_alias(db, user.id, tx.description, tx.merchant_normalized)
    after = _transaction_snapshot(tx)
    log_event(
        db, user_id=user.id, action="update", resource_type="transaction",
        resource_id=tx.id, details={"before": before, "after": after}, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(tx)
    logger.info("transaction.updated user=%s id=%s", user.id, tx.id)
    return tx


@app.post("/transactions/{transaction_id}/undo", response_model=TransactionOut)
def undo_transaction_update(
    transaction_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Restore the latest transaction update, if it has not already been undone."""
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    latest_event = (
        db.query(AuditLog)
        .filter(
            AuditLog.user_id == user.id,
            AuditLog.resource_type == "transaction",
            AuditLog.resource_id == transaction_id,
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .first()
    )
    if not latest_event or latest_event.action != "update" or not latest_event.details:
        raise HTTPException(status_code=409, detail="No reversible transaction update is available")
    try:
        details = json.loads(latest_event.details)
        before = details["before"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="The latest transaction update cannot be reversed") from exc

    try:
        restored = TransactionIn(**before).model_dump()
    except Exception as exc:
        raise HTTPException(status_code=409, detail="The saved transaction version is invalid") from exc
    if restored.get("account_id"):
        account = db.get(Account, restored["account_id"])
        if not account or account.user_id != user.id:
            raise HTTPException(status_code=409, detail="The saved account is no longer available")
    for key, value in restored.items():
        setattr(tx, key, value)
    # These fields are intentionally not accepted from ordinary user edits, but
    # they are part of the exact version being restored after a category fix.
    tx.merchant_normalized = before.get("merchant_normalized")
    tx.confidence = before.get("confidence")
    log_event(
        db,
        user_id=user.id,
        action="undo",
        resource_type="transaction",
        resource_id=tx.id,
        details={"source_audit_id": latest_event.id},
        ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(tx)
    llm_cache.invalidate_user(user.id)
    logger.info("transaction.undo user=%s id=%s source_audit=%s", user.id, tx.id, latest_event.id)
    return tx


# ── Audit Log ─────────────────────────────────────────────────────────────────
@app.get("/audit", response_model=list[AuditLogOut])
def list_audit_logs(
    resource_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return get_audit_trail(db, user.id, resource_type=resource_type, limit=limit, offset=offset)


# ── Webhooks ──────────────────────────────────────────────────────────────────
@app.get("/webhooks", response_model=list[WebhookOut])
def list_webhooks(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Webhook).filter(Webhook.user_id == user.id).order_by(Webhook.created_at.desc()).all()


@app.post("/webhooks", response_model=WebhookOut, status_code=201)
def create_webhook(
    payload: WebhookIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # SSRF guard: reject URLs that resolve to loopback/private/metadata addresses.
    try:
        validate_webhook_url(payload.url)
    except UnsafeURLError as e:
        raise HTTPException(status_code=400, detail=f"Unsafe webhook URL: {e}") from e

    hook = Webhook(user_id=user.id, **payload.model_dump())
    db.add(hook)
    log_event(
        db,
        user_id=user.id,
        action="create",
        resource_type="webhook",
        resource_id=hook.id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    db.refresh(hook)
    logger.info("webhook.created user=%s id=%s url=%s", user.id, hook.id, hook.url[:60])
    return hook


@app.delete("/webhooks/{webhook_id}")
def delete_webhook(
    webhook_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    hook = db.get(Webhook, webhook_id)
    if not hook or hook.user_id != user.id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(hook)
    log_event(
        db,
        user_id=user.id,
        action="delete",
        resource_type="webhook",
        resource_id=webhook_id,
        ip_address=request.client.host if request.client else None,
    )
    db.commit()
    return {"deleted": True}


# ── GST Report ────────────────────────────────────────────────────────────────
@app.get("/gst/report", response_model=GSTReportOut)
def gst_report(
    month: str | None = Query(None),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id, month).all()
    return generate_gst_report(transactions)


# ── Export ─────────────────────────────────────────────────────────────────────
@app.get("/export/{fmt}")
def export_data(
    fmt: str,
    month: str | None = Query(None),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Keep the legacy parameterized route compatible with the static full-data
    # export even when route registration order puts this handler first.
    if fmt == "full":
        return export_full_data(user, db)
    transactions = _tx_query(db, user.id, month).all()
    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions to export")

    if fmt == "csv":
        content = export_csv(transactions)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=ledger_export.csv"},
        )
    elif fmt == "json":
        content = export_json(transactions)
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=ledger_export.json"},
        )
    elif fmt == "tally":
        content = export_tally_xml(transactions)
        return Response(
            content=content,
            media_type="application/xml",
            headers={"Content-Disposition": "attachment; filename=ledger_tally.xml"},
        )
    else:
        raise HTTPException(status_code=400, detail="Format must be csv, json, or tally")


@app.get("/export/full")
def export_full_data(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Export the user's portable data without secrets or uploaded statement payloads."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Profile not found")
    transactions = _tx_query(db, user.id, include_unposted=True).order_by(Transaction.date.asc()).all()
    conversations = db.query(AIConversation).filter(AIConversation.user_id == user.id).all()
    payload = {
        "export_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "profile": {
            "id": db_user.id,
            "email": db_user.email,
            "display_name": db_user.display_name,
            "avatar_url": db_user.avatar_url,
            "currency_preference": db_user.currency_preference,
            "created_at": db_user.created_at.isoformat() if db_user.created_at else None,
        },
        "accounts": [
            {
                "id": a.id, "name": a.name, "account_type": a.account_type,
                "institution": a.institution, "balance": str(a.balance), "currency": a.currency,
                "is_active": a.is_active, "last_reconciled_at": a.last_reconciled_at.isoformat() if a.last_reconciled_at else None,
                "last_reconciled_balance": str(a.last_reconciled_balance) if a.last_reconciled_balance is not None else None,
                "reconciliation_note": a.reconciliation_note,
            }
            for a in db.query(Account).filter(Account.user_id == user.id).all()
        ],
        "transactions": json.loads(export_json(transactions))["transactions"],
        "budgets": [
            {"id": b.id, "category": b.category, "monthly_limit": str(b.monthly_limit), "strategy": b.strategy}
            for b in db.query(Budget).filter(Budget.user_id == user.id).all()
        ],
        "merchant_aliases": [
            {"id": a.id, "alias": a.alias_key, "canonical": a.canonical,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id).all()
        ],
        "categories": [
            {"id": c.id, "name": c.name, "kind": c.kind, "reporting_group": c.reporting_group,
             "is_active": c.is_active, "created_at": c.created_at.isoformat() if c.created_at else None}
            for c in db.query(UserCategory).filter(UserCategory.user_id == user.id).all()
        ],
        "recurring_rules": [_recurring_payload(rule) for rule in db.query(RecurringRule).filter(RecurringRule.user_id == user.id).all()],
        "goals": [
            {"id": g.id, "name": g.name, "goal_type": g.goal_type, "target_amount": str(g.target_amount),
             "current_amount": str(g.current_amount), "deadline": g.deadline.isoformat() if g.deadline else None, "status": g.status}
            for g in db.query(Goal).filter(Goal.user_id == user.id).all()
        ],
        "portfolios": [
            {"id": p.id, "name": p.name, "portfolio_type": p.portfolio_type,
             "holdings": [
                 {"id": h.id, "symbol": h.symbol, "name": h.name, "quantity": str(h.quantity),
                  "buy_price": str(h.buy_price), "current_price": str(h.current_price), "asset_type": h.asset_type,
                  "purchase_date": h.purchase_date.isoformat() if h.purchase_date else None, "notes": h.notes}
                 for h in p.holdings
             ]}
            for p in db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
        ],
        "conversations": [
            {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat() if c.created_at else None,
             "messages": [{"id": m.id, "role": m.role, "content": m.content,
                           "created_at": m.created_at.isoformat() if m.created_at else None} for m in c.messages]}
            for c in conversations
        ],
        "imports": [
            {"id": j.id, "status": j.status, "file_name": j.file_name, "file_extension": j.file_extension,
             "account_id": j.account_id, "row_count": j.row_count, "error_message": j.error_message,
             "created_at": j.created_at.isoformat() if j.created_at else None,
             "updated_at": j.updated_at.isoformat() if j.updated_at else None}
            for j in db.query(ImportJob).filter(ImportJob.user_id == user.id).all()
        ],
        "webhooks": [
            {"id": w.id, "url": w.url, "events": w.events, "is_active": w.is_active,
             "last_triggered": w.last_triggered.isoformat() if w.last_triggered else None,
             "failure_count": w.failure_count, "created_at": w.created_at.isoformat() if w.created_at else None}
            for w in db.query(Webhook).filter(Webhook.user_id == user.id).all()
        ],
        "category_corrections": [
            {"description_hash": c.description_hash, "category": c.category, "correction_count": c.correction_count}
            for c in db.query(CategoryCorrection).filter(CategoryCorrection.user_id == user.id).all()
        ],
        "audit_log": [
            {"action": a.action, "resource_type": a.resource_type, "resource_id": a.resource_id,
             "details": a.details, "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in db.query(AuditLog).filter(AuditLog.user_id == user.id).order_by(AuditLog.created_at.asc()).all()
        ],
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=ledger_full_export.json"},
    )


@app.delete("/profile/data")
def delete_all_user_data(
    payload: DataDeletionRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Permanently erase all Ledger data for the signed-in user after explicit confirmation."""
    db_user = db.get(User, user.id)
    if not db_user:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Delete dependents explicitly so this remains safe on databases without
    # database-level ON DELETE CASCADE configuration.
    portfolio_ids = [p.id for p in db.query(Portfolio.id).filter(Portfolio.user_id == user.id).all()]
    if portfolio_ids:
        db.query(Holding).filter(Holding.portfolio_id.in_(portfolio_ids)).delete(synchronize_session=False)
    conversation_ids = [c.id for c in db.query(AIConversation.id).filter(AIConversation.user_id == user.id).all()]
    if conversation_ids:
        db.query(AIMessage).filter(AIMessage.conversation_id.in_(conversation_ids)).delete(synchronize_session=False)
    counts = {
        "transactions": db.query(Transaction).filter(Transaction.user_id == user.id).delete(synchronize_session=False),
        "accounts": db.query(Account).filter(Account.user_id == user.id).delete(synchronize_session=False),
        "budgets": db.query(Budget).filter(Budget.user_id == user.id).delete(synchronize_session=False),
        "merchant_aliases": db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id).delete(synchronize_session=False),
        "categories": db.query(UserCategory).filter(UserCategory.user_id == user.id).delete(synchronize_session=False),
        "recurring_rules": db.query(RecurringRule).filter(RecurringRule.user_id == user.id).delete(synchronize_session=False),
        "goals": db.query(Goal).filter(Goal.user_id == user.id).delete(synchronize_session=False),
        "imports": db.query(ImportJob).filter(ImportJob.user_id == user.id).delete(synchronize_session=False),
        "webhooks": db.query(Webhook).filter(Webhook.user_id == user.id).delete(synchronize_session=False),
        "portfolios": db.query(Portfolio).filter(Portfolio.user_id == user.id).delete(synchronize_session=False),
        "conversations": db.query(AIConversation).filter(AIConversation.user_id == user.id).delete(synchronize_session=False),
        "category_corrections": db.query(CategoryCorrection).filter(CategoryCorrection.user_id == user.id).delete(synchronize_session=False),
        "audit_logs": db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(synchronize_session=False),
    }
    db.delete(db_user)
    db.commit()
    llm_cache.invalidate_user(user.id)
    logger.info("profile.data_deleted user=%s counts=%s", user.id, counts)
    return {"deleted": True, "counts": counts}


# ── Portfolios ────────────────────────────────────────────────────────────────
@app.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Portfolio).filter(Portfolio.user_id == user.id).order_by(Portfolio.created_at.desc()).all()


@app.post("/portfolios", response_model=PortfolioOut, status_code=201)
def create_portfolio(
    payload: PortfolioIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = Portfolio(user_id=user.id, **payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@app.delete("/portfolios/{portfolio_id}")
def delete_portfolio(
    portfolio_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    db.delete(p)
    log_event(
        db, user_id=user.id, action="delete", resource_type="portfolio",
        resource_id=portfolio_id, ip_address=_client_ip(request),
    )
    db.commit()
    return {"deleted": True}


# ── Holdings ──────────────────────────────────────────────────────────────────
@app.get("/portfolios/{portfolio_id}/holdings", response_model=list[HoldingOut])
def list_holdings(
    portfolio_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return p.holdings


@app.post("/portfolios/{portfolio_id}/holdings", response_model=HoldingOut, status_code=201)
def add_holding(
    portfolio_id: str,
    payload: HoldingIn,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    h = Holding(portfolio_id=portfolio_id, **payload.model_dump())
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@app.put("/holdings/{holding_id}", response_model=HoldingOut)
def update_holding(
    holding_id: str,
    payload: HoldingIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    h = db.get(Holding, holding_id)
    if not h:
        raise HTTPException(status_code=404, detail="Holding not found")
    p = db.get(Portfolio, h.portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not authorized")
    for k, v in payload.model_dump().items():
        setattr(h, k, v)
    log_event(
        db, user_id=user.id, action="update", resource_type="holding",
        resource_id=holding_id, ip_address=_client_ip(request),
    )
    db.commit()
    db.refresh(h)
    return h


@app.delete("/holdings/{holding_id}")
def delete_holding(
    holding_id: str,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    h = db.get(Holding, holding_id)
    if not h:
        raise HTTPException(status_code=404, detail="Holding not found")
    p = db.get(Portfolio, h.portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Not authorized")
    db.delete(h)
    log_event(
        db, user_id=user.id, action="delete", resource_type="holding",
        resource_id=holding_id, ip_address=_client_ip(request),
    )
    db.commit()
    return {"deleted": True}


# ── Portfolio Summary ─────────────────────────────────────────────────────────
@app.get("/portfolios/summary")
def portfolio_summary(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    portfolios = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .filter(Portfolio.user_id == user.id)
        .all()
    )
    total_invested = 0
    total_current = 0
    by_type = {}

    for p in portfolios:
        for h in p.holdings:
            invested = float(h.quantity * h.buy_price)
            current = float(h.quantity * h.current_price)
            total_invested += invested
            total_current += current
            by_type.setdefault(h.asset_type, {"invested": 0, "current": 0, "count": 0})
            by_type[h.asset_type]["invested"] += invested
            by_type[h.asset_type]["current"] += current
            by_type[h.asset_type]["count"] += 1

    return {
        "total_invested": round(total_invested, 2),
        "total_current": round(total_current, 2),
        "total_pnl": round(total_current - total_invested, 2),
        "total_pnl_pct": round(((total_current - total_invested) / max(total_invested, 1)) * 100, 2),
        "by_type": by_type,
        "portfolio_count": len(portfolios),
    }


# ── Credit Health ─────────────────────────────────────────────────────────────
@app.get("/credit-health", response_model=CreditHealthOut)
def credit_health(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id).limit(500).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    accounts = db.query(Account).filter(Account.user_id == user.id, Account.is_active).all()
    return compute_credit_health(transactions, budgets, accounts)


# ── Bill Negotiator ───────────────────────────────────────────────────────────
@app.get("/bills/negotiate")
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
    return await analyze_bills(recurring)


# ── Community Benchmarks ──────────────────────────────────────────────────────
@app.get("/benchmarks", response_model=BenchmarkOut)
def community_benchmarks(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id).limit(500).all()
    return generate_benchmarks(transactions)


# ── Anomaly Detection ─────────────────────────────────────────────────────────
@app.get("/analytics/anomalies")
def get_anomalies(
    range: str | None = Query("3m", pattern="^(this_month|30d|3m|1y|all|current_year)$"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detect anomalous transactions using IQR + velocity spike analysis."""
    cache_key = f"{user.id}:anomalies:{range}"
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

    anomalies = detect_anomalies(transactions)
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
@app.get("/analytics/forecast")
def get_forecast(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Project 30/60/90-day spending per category using EWMA."""
    cache_key = f"{user.id}:forecast"
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


@app.post("/analytics/scenario", response_model=ScenarioOut)
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
        category=payload.category,
        reduction_pct=payload.reduction_pct,
        income_change_pct=payload.income_change_pct,
        one_time_expense=payload.one_time_expense,
        horizon_months=payload.horizon_months,
    )


@app.get("/analytics/compare")
def analytics_compare(
    days: int = Query(30, ge=7, le=365),
    end: date | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compare two equal-length periods with evidence and sufficiency metadata."""
    transactions = _tx_query(db, user.id).all()
    return compare_periods(transactions, end_date=end, days=days)


# ── Portfolio Analytics ───────────────────────────────────────────────────────
@app.get("/portfolios/analytics")
def portfolio_analytics(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute Sharpe ratio, XIRR, asset allocation, drawdown for all portfolios."""
    portfolios = (
        db.query(Portfolio)
        .options(selectinload(Portfolio.holdings))
        .filter(Portfolio.user_id == user.id)
        .all()
    )
    if not portfolios:
        return {"allocation": [], "total_return_pct": 0, "sharpe_ratio": None}

    holdings_by_portfolio = {p.id: p.holdings for p in portfolios}
    return compute_portfolio_analytics(portfolios, holdings_by_portfolio)


# ── Proactive Insights (upgraded — with anomaly + forecast context) ────────────
@app.get("/insights/proactive", response_model=list[ProactiveInsight])
@limiter.limit(settings.insights_rate_limit)
async def proactive_insights_v2(
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI-powered proactive insights with anomaly and forecast injection."""
    # Check cache first (insight_cache_ttl_hours)
    cache_key = f"{user.id}:proactive"
    cached = llm_cache.get(cache_key)
    if cached:
        return cached

    transactions = _tx_query(db, user.id).limit(300).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()

    # Enrich with anomalies and forecast
    anomalies = detect_anomalies(transactions)
    forecast = generate_forecast(transactions)

    started = time.perf_counter()
    result = await generate_proactive_insights(transactions, budgets, anomalies, forecast)
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


@app.post("/insights/feedback")
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


# ── Category Correction (user feedback for learning) ─────────────────────────
@app.post("/transactions/{transaction_id}/correct-category")
def correct_transaction_category(
    transaction_id: str,
    payload: CategoryCorrectionRequest,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User manually corrects a transaction's category — trains the learning system."""
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    old_category = tx.category
    before = _transaction_snapshot(tx)
    tx.category = payload.category
    tx.confidence = 1.0  # User correction = full confidence
    after = _transaction_snapshot(tx)
    log_event(
        db,
        user_id=user.id,
        action="update",
        resource_type="transaction",
        resource_id=tx.id,
        details={"before": before, "after": after, "reason": "category_correction"},
        ip_address=_client_ip(request),
    )
    record_telemetry("transaction.correction", user_id=user.id, outcome="category", metadata={"status": "completed"})
    db.commit()

    # Record correction for learning pipeline
    record_correction(db, user.id, tx.description, payload.category)

    # Invalidate relevant caches for this user
    llm_cache.invalidate_user(user.id)

    logger.info(
        "category.corrected user=%s tx=%s %s→%s",
        user.id,
        transaction_id,
        old_category,
        payload.category,
    )
    return {"corrected": True, "old_category": old_category, "new_category": payload.category}


# ── Embedding Cache Stats (debug/monitoring) ──────────────────────────────────
@app.get("/debug/embedding-cache")
def embedding_cache_stats(
    user: UserContext = Depends(get_current_user),
):
    """Return embedding cache statistics for monitoring."""
    from .services.embedding_cache import embedding_cache

    return embedding_cache.get_stats()


# ── Mass Recategorize (new categories support) ────────────────────────────────
@app.post("/categorize/recategorize")
@limiter.limit(settings.categorize_rate_limit)
async def recategorize_uncategorized(
    request: Request,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-categorize 'Other' transactions using the 4-tier AI pipeline."""
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user.id,
            Transaction.category == "Other",
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    if not txs:
        return {"updated": 0, "offset": offset}

    # Load user overrides for personalized categorization
    user_overrides = get_user_overrides(db, user.id)
    batch = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in txs]
    results = await categorize_batch(batch, user_overrides=user_overrides)

    updated = 0
    for result in results:
        if result["category"] != "Other" and result.get("confidence", 0) >= 0.6:
            tx = db.get(Transaction, result["id"])
            if tx:
                tx.category = result["category"]
                tx.confidence = result.get("confidence")
                tx.merchant_normalized = result.get("merchant")
                updated += 1
    db.commit()
    logger.info("recategorize user=%s updated=%d of %d offset=%d", user.id, updated, len(txs), offset)
    return {"updated": updated, "total_checked": len(txs), "offset": offset, "has_more": len(txs) == limit}


# ── Outermost ASGI CORS Wrap ──────────────────────────────────────────────────
# We wrap the FastAPI app instance at the ASGI level. This places CORSMiddleware
# outside of Starlette's ServerErrorMiddleware, ensuring that even unhandled 500
# exceptions receive CORS headers and don't get blocked by the browser.
app = CORSMiddleware(
    app,
    allow_origins=settings.get_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

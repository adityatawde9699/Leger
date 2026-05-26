import asyncio
import base64
import hashlib
import json
import logging
import sys
import time
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from .auth import get_current_user
from .config import settings
from .db import Base, engine, get_db
from .models import (
    Account,
    AIConversation,
    AIMessage,
    Budget,
    Holding,
    ImportJob,
    Portfolio,
    Transaction,
    User,
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
    GSTReportOut,
    HoldingIn,
    HoldingOut,
    ImportJobOut,
    MessageOut,
    PaginatedTransactions,
    PortfolioIn,
    PortfolioOut,
    ProactiveInsight,
    ProfileStatsOut,
    SmsParseRequest,
    SmsWebhookRequest,
    TransactionIn,
    TransactionOut,
    UserContext,
    UserProfileIn,
    UserProfileOut,
    WebhookIn,
    WebhookOut,
)
from .services.ai_router import ai_router
from .services.anomaly_detector import detect_anomalies
from .services.audit import get_audit_trail, log_event
from .services.auto_categorizer import categorize_batch, categorize_single
from .services.benchmarks import generate_benchmarks
from .services.bill_negotiator import analyze_bills
from .services.categorization_learner import get_user_overrides, record_correction
from .services.credit_health import compute_credit_health
from .services.export import export_csv, export_json, export_tally_xml
from .services.forecaster import budget_breach_warnings, generate_forecast
from .services.gst import generate_gst_report
from .services.insights import (
    SYSTEM_PROMPT,
    build_advisor_context,
    compute_insights,
    dynamic_budget_suggestions,
    monthly_summary,
    recurring_payments,
)
from .services.portfolio_analytics import compute_portfolio_analytics
from .services.proactive_insights import generate_proactive_insights
from .services.prompt_guard import build_safe_messages, sanitize_user_input
from .services.receipt_ocr import parse_receipt_image
from .services.sms_parser import parse_sms
from .services.statements import parse_csv, parse_excel, parse_pdf


# ── Tiered TTL Cache (L1: in-memory with TTL) ─────────────────────────────────
class TTLCache:
    """LRU cache with per-entry TTL expiry and user-scoped keys."""

    def __init__(self, maxsize: int = 512, default_ttl: int = 3600):
        self._cache: dict[str, dict] = {}
        self.maxsize    = maxsize
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
            "data":    value,
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
# NOTE: In production, use `alembic upgrade head` instead.
Base.metadata.create_all(bind=engine)

# ── Rate limiter ──────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Ledger API", version="1.0.1", docs_url="/docs")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _month_range(month: str) -> tuple[date, date]:
    start = date.fromisoformat(f"{month}-01")
    if start.month == 12:
        end = date(start.year + 1, 1, 1)
    else:
        end = date(start.year, start.month + 1, 1)
    return start, end


def _tx_query(db: Session, user_id: str, month: str | None = None):
    q = db.query(Transaction).filter(Transaction.user_id == user_id)
    if month:
        start, end = _month_range(month)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    return q.order_by(Transaction.date.desc(), Transaction.created_at.desc())


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
    from sqlalchemy import and_, func, or_

    # ── Step 1: find the anchor row ──
    anchor_q = db.query(Transaction).filter(
        Transaction.user_id == user_id,
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

    post_q = db.query(Transaction).filter(
        Transaction.user_id == user_id,
        Transaction.id != anchor.id,
        Transaction.source != "cash",
        after_filter,
    )
    if as_of_date:
        post_q = post_q.filter(Transaction.date < as_of_date)
    if exclude_id:
        post_q = post_q.filter(Transaction.id != exclude_id)

    net_change = Decimal("0")
    for tx in post_q.all():
        if tx.type == "income":
            net_change += tx.amount
        else:
            net_change -= tx.amount

    return anchor.running_balance + net_change


def _history_start(range_key: str | None) -> date | None:
    from datetime import date as dt_date
    from datetime import timedelta

    today = dt_date.today()
    if range_key == "this_month":
        return today.replace(day=1)
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
    direction = "income" if tx.type == "income" else "expense"
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


# ── Keep-alive ping (Render free tier cold-start prevention) ─────────────────
@app.get("/ping")
def ping():
    """Lightweight health check / keep-alive. No DB, no auth. ~0ms overhead."""
    return {"pong": True}


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "version": "1.0.1"}


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
    total_txns = db.query(func.count(Transaction.id)).filter(
        Transaction.user_id == user.id
    ).scalar() or 0
    total_income = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user.id, Transaction.type == "income"
    ).scalar() or Decimal("0")
    total_expenses = db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter(
        Transaction.user_id == user.id, Transaction.type == "expense"
    ).scalar() or Decimal("0")
    accounts_count = db.query(func.count(Account.id)).filter(
        Account.user_id == user.id, Account.is_active.is_(True)
    ).scalar() or 0
    budgets_count = db.query(func.count(Budget.id)).filter(
        Budget.user_id == user.id
    ).scalar() or 0

    return ProfileStatsOut(
        total_transactions=total_txns,
        total_income=total_income,
        total_expenses=total_expenses,
        net_balance=total_income - total_expenses,
        accounts_count=accounts_count,
        budgets_count=budgets_count,
    )


# ── Transactions ──────────────────────────────────────────────────────────────
@app.get("/transactions", response_model=PaginatedTransactions)
def list_transactions(
    cursor: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    month: str | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    tx_type: str | None = Query(None, alias="type"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Transaction).filter(Transaction.user_id == user.id)

    if month:
        start, end = _month_range(month)
        q = q.filter(Transaction.date >= start, Transaction.date < end)
    if category:
        q = q.filter(Transaction.category == category)
    if tx_type and tx_type in ("income", "expense"):
        q = q.filter(Transaction.type == tx_type)
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
    tx = Transaction(user_id=user.id, **payload.model_dump())
    db.add(tx)
    db.flush()  # assign tx.id before backfill query

    # Backfill running_balance so the DB is always the source of truth.
    # running_balance = (last known balance) ± this transaction's amount.
    if tx.running_balance is None and tx.source != "cash":
        prior_balance = _get_balance_at(db, user.id, as_of_date=None, exclude_id=tx.id)
        if prior_balance is not None:
            if tx.type == "income":
                tx.running_balance = prior_balance + tx.amount
            else:
                tx.running_balance = prior_balance - tx.amount

    db.commit()
    db.refresh(tx)
    logger.info("transaction.created user=%s id=%s amount=%s balance=%s", user.id, tx.id, tx.amount, tx.running_balance)
    return tx


@app.delete("/transactions/{transaction_id}")
def delete_transaction(
    transaction_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    db.commit()
    logger.info("transaction.deleted user=%s id=%s", user.id, transaction_id)
    return {"deleted": True}


@app.post("/transactions/bulk-delete")
def bulk_delete_transactions(
    payload: BulkDeleteRequest,
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


@app.put("/budgets", response_model=list[BudgetOut])
def upsert_budgets(
    payload: list[BudgetIn],
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
    q = db.query(Transaction).filter(Transaction.user_id == user.id, Transaction.type == "expense")
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

    return {
        **summary,
        "insights": compute_insights(transactions, budgets),
        "recurring": recurring_payments(transactions),
    }


# ── SMS Import ────────────────────────────────────────────────────────────────
@app.post("/imports/sms", response_model=list[TransactionOut])
def import_sms(
    payload: SmsParseRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = []
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
        saved.append(tx)
    db.commit()
    for tx in saved:
        db.refresh(tx)
    logger.info("sms.import user=%s imported=%d", user.id, len(saved))
    return saved


@app.post("/imports/sms/webhook", response_model=list[TransactionOut])
def import_sms_webhook(
    payload: SmsWebhookRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive SMS payloads from an Android companion bridge and reuse the SMS parser."""
    saved = []
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
        saved.append(tx)
    db.commit()
    for tx in saved:
        db.refresh(tx)
    logger.info("sms.webhook user=%s device=%s imported=%d", user.id, payload.device_id, len(saved))
    return saved


# ── Statement Import (async job) ──────────────────────────────────────────────
@app.post("/imports/statement", response_model=ImportJobOut, status_code=202)
async def import_statement(
    file: UploadFile = File(...),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    ext = file.filename.lower().rsplit(".", 1)[-1]
    if ext not in ("csv", "pdf", "xls", "xlsx"):
        raise HTTPException(status_code=400, detail="Upload a CSV, Excel, or PDF statement")
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10MB)")

    content = await file.read()

    # Create import job record
    job = ImportJob(user_id=user.id, file_name=file.filename, status="processing")
    db.add(job)
    db.commit()
    db.refresh(job)

    # Process synchronously for now (Celery in Phase 2)
    # Run in thread pool to avoid blocking event loop
    async def _process():
        try:
            if ext == "csv":
                rows = parse_csv(content)
            elif ext in ("xls", "xlsx"):
                rows = parse_excel(content)
            else:
                rows = await parse_pdf(content)

            saved_count = 0
            for seq, row in enumerate(rows):
                row["stmt_seq"] = seq  # preserve bank statement row order
                validated = TransactionIn(**row).model_dump()
                # SHA-256 dedup on date+amount+description
                fingerprint = hashlib.sha256(
                    f"{validated['date']}{validated['amount']}{validated['description']}".encode()
                ).hexdigest()
                validated["source_ref"] = fingerprint

                duplicate = (
                    db.query(Transaction)
                    .filter(
                        Transaction.user_id == user.id,
                        Transaction.source == "statement",
                        Transaction.source_ref == fingerprint,
                    )
                    .first()
                )
                if not duplicate:
                    new_tx = Transaction(user_id=user.id, **validated)
                    # Backfill running_balance for rows where the parsed PDF/CSV
                    # had no Balance column (e.g. receipt PDFs, Spotify invoices).
                    if new_tx.running_balance is None and new_tx.source != "cash":
                        prior_bal = _get_balance_at(db, user.id, as_of_date=None)
                        if prior_bal is not None:
                            if new_tx.type == "income":
                                new_tx.running_balance = prior_bal + new_tx.amount
                            else:
                                new_tx.running_balance = prior_bal - new_tx.amount
                    db.add(new_tx)
                    saved_count += 1

            db.commit()
            if not rows:
                job.status = "failed"
                job.error_message = (
                    "No transactions could be extracted from this file. "
                    "If this is a scanned/image PDF, install Tesseract OCR on your system "
                    "(https://github.com/UB-Mannheim/tesseract/wiki) for OCR support. "
                    "Alternatively, export a digital/text-layer PDF or CSV from your bank."
                )
            else:
                job.status = "done"
                job.row_count = saved_count

        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)[:500]
            logger.exception("import.failed job=%s", job.id)
        finally:
            db.commit()

    asyncio.create_task(_process())
    logger.info("import.started user=%s job=%s file=%s", user.id, job.id, file.filename)
    return job


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

    if _wants_last_transaction(question):
        latest = transactions[0] if transactions else None
        answer = _format_transaction(latest) if latest else "No transactions were found for this signed-in account."

        async def last_tx_event_generator():
            yield f"data: {answer}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            last_tx_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    if _wants_overspending(question):
        answer = _format_overspending(transactions)

        async def overspending_event_generator():
            yield f"data: {answer}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            overspending_event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache"},
        )

    # Enrich advisor context with anomalies + forecast
    anomalies = detect_anomalies(transactions)
    forecast  = generate_forecast(transactions)
    context   = build_advisor_context(transactions, budgets, anomalies=anomalies, forecast=forecast)


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

    # Simple hashing of the complete message context
    cache_key = hashlib.sha256(json.dumps(messages).encode()).hexdigest()
    cached_reply = llm_cache.get(cache_key)

    if cached_reply:
        logger.info("Cache hit for advisor stream.")

        async def cached_event_generator():
            # Yield cached string fully
            yield f"data: {cached_reply}\n\n"

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
            async for token in ai_router.stream(SYSTEM_PROMPT, messages):
                full_reply.append(token)
                yield f"data: {token}\n\n"
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
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    for k, v in payload.model_dump().items():
        setattr(acct, k, v)
    db.commit()
    db.refresh(acct)
    return acct


@app.delete("/accounts/{account_id}")
def delete_account(
    account_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acct = db.get(Account, account_id)
    if not acct or acct.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    acct.is_active = False  # soft delete
    db.commit()
    logger.info("account.deleted user=%s id=%s", user.id, account_id)
    return {"deleted": True}


# ── Auto-categorize ──────────────────────────────────────────────────────────
@app.post("/categorize", response_model=CategorizeSingleResponse)
async def auto_categorize(
    payload: CategorizeSingleRequest,
    user: UserContext = Depends(get_current_user),
):
    result = await categorize_single(payload.description, payload.tx_type)
    return result


@app.post("/categorize/batch")
async def auto_categorize_batch(
    payload: CategorizeBatchRequest,
    user: UserContext = Depends(get_current_user),
):
    results = await categorize_batch(payload.transactions)
    return results



# ── Proactive Insights ───────────────────────────────────────────────────────
# Proactive insights moved to end of file (v2 with anomaly + forecast context)


# ── Receipt OCR ───────────────────────────────────────────────────────────────
@app.post("/receipts/scan")
async def scan_receipt(
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
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")
    for k, v in payload.model_dump().items():
        setattr(tx, k, v)
    db.commit()
    db.refresh(tx)
    logger.info("transaction.updated user=%s id=%s", user.id, tx.id)
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
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    db.delete(p)
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
    db.commit()
    db.refresh(h)
    return h


@app.delete("/holdings/{holding_id}")
def delete_holding(
    holding_id: str,
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
    db.commit()
    return {"deleted": True}


# ── Portfolio Summary ─────────────────────────────────────────────────────────
@app.get("/portfolios/summary")
def portfolio_summary(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
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
async def negotiate_bills(
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
    range: str | None = Query("3m", pattern="^(this_month|3m|1y|all)$"),
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detect anomalous transactions using IQR + velocity spike analysis."""
    cache_key = f"{user.id}:anomalies:{range}"
    cached = llm_cache.get(cache_key)
    if cached:
        return cached

    start = _history_start(range)
    q = db.query(Transaction).filter(Transaction.user_id == user.id)
    if start:
        q = q.filter(Transaction.date >= start)
    transactions = q.order_by(Transaction.date.desc()).all()

    anomalies = detect_anomalies(transactions)
    llm_cache.put(cache_key, anomalies, ttl=1800)  # 30-min cache
    return anomalies


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
    budgets      = db.query(Budget).filter(Budget.user_id == user.id).all()
    forecast     = generate_forecast(transactions)
    warnings     = budget_breach_warnings(transactions, budgets)
    result       = {**forecast, "budget_warnings": warnings}

    llm_cache.put(cache_key, result, ttl=3600)
    return result


# ── Portfolio Analytics ───────────────────────────────────────────────────────
@app.get("/portfolios/analytics")
def portfolio_analytics(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Compute Sharpe ratio, XIRR, asset allocation, drawdown for all portfolios."""
    portfolios = db.query(Portfolio).filter(Portfolio.user_id == user.id).all()
    if not portfolios:
        return {"allocation": [], "total_return_pct": 0, "sharpe_ratio": None}

    holdings_by_portfolio = {p.id: p.holdings for p in portfolios}
    return compute_portfolio_analytics(portfolios, holdings_by_portfolio)


# ── Proactive Insights (upgraded — with anomaly + forecast context) ────────────
@app.get("/insights/proactive", response_model=list[ProactiveInsight])
async def proactive_insights_v2(
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
    budgets      = db.query(Budget).filter(Budget.user_id == user.id).all()

    # Enrich with anomalies and forecast
    anomalies = detect_anomalies(transactions)
    forecast  = generate_forecast(transactions)

    result = await generate_proactive_insights(transactions, budgets, anomalies, forecast)
    llm_cache.put(cache_key, result, ttl=settings.insight_cache_ttl_hours * 3600)
    return result


# ── Category Correction (user feedback for learning) ─────────────────────────
@app.post("/transactions/{transaction_id}/correct-category")
def correct_transaction_category(
    transaction_id: str,
    payload: CategoryCorrectionRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """User manually corrects a transaction's category — trains the learning system."""
    tx = db.get(Transaction, transaction_id)
    if not tx or tx.user_id != user.id:
        raise HTTPException(status_code=404, detail="Transaction not found")

    old_category = tx.category
    tx.category  = payload.category
    tx.confidence = 1.0  # User correction = full confidence
    db.commit()

    # Record correction for learning pipeline
    record_correction(db, user.id, tx.description, payload.category)

    # Invalidate relevant caches for this user
    llm_cache.invalidate_user(user.id)

    logger.info(
        "category.corrected user=%s tx=%s %s→%s",
        user.id, transaction_id, old_category, payload.category,
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
async def recategorize_uncategorized(
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
                tx.category           = result["category"]
                tx.confidence         = result.get("confidence")
                tx.merchant_normalized = result.get("merchant")
                updated += 1
    db.commit()
    logger.info("recategorize user=%s updated=%d of %d offset=%d", user.id, updated, len(txs), offset)
    return {"updated": updated, "total_checked": len(txs), "offset": offset, "has_more": len(txs) == limit}


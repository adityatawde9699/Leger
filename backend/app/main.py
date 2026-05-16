import asyncio
import base64
import hashlib
import logging
import sys
from datetime import date
from decimal import Decimal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from .auth import get_current_user
from .config import settings
from .db import Base, engine, get_db
from .models import Account, AIConversation, AIMessage, AuditLog, Budget, Holding, ImportJob, Portfolio, Transaction, Webhook
from .schemas import (
    AccountIn,
    AccountOut,
    AdvisorRequest,
    AuditLogOut,
    BenchmarkOut,
    BudgetIn,
    BudgetOut,
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
    ReceiptResult,
    SmsParseRequest,
    TransactionIn,
    TransactionOut,
    UserContext,
    WebhookIn,
    WebhookOut,
)
from .services.ai_router import ai_router
from .services.auto_categorizer import categorize_batch, categorize_single
from .services.insights import (
    SYSTEM_PROMPT,
    build_advisor_context,
    compute_insights,
    dynamic_budget_suggestions,
    monthly_summary,
    recurring_payments,
)
from .services.proactive_insights import generate_proactive_insights
from .services.prompt_guard import build_safe_messages, sanitize_user_input
from .services.receipt_ocr import parse_receipt_image
from .services.audit import get_audit_trail, log_event
from .services.benchmarks import generate_benchmarks
from .services.bill_negotiator import analyze_bills
from .services.credit_health import compute_credit_health
from .services.export import export_csv, export_json, export_tally_xml
from .services.gst import compute_gst, generate_gst_report
from .services.sms_parser import parse_sms
from .services.statements import parse_csv, parse_pdf
from .services.webhook_dispatcher import fire_event

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
app = FastAPI(title="Ledger API", version="2.0.0", docs_url="/docs")
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


def _cursor_encode(tx: Transaction) -> str:
    return base64.urlsafe_b64encode(f"{tx.date}|{tx.id}".encode()).decode()


def _cursor_decode(cursor: str) -> tuple[date, str]:
    decoded = base64.urlsafe_b64decode(cursor.encode()).decode()
    date_str, tx_id = decoded.split("|", 1)
    return date.fromisoformat(date_str), tx_id


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"ok": True, "version": "2.0.0", "ai_local": settings.llama_enabled}


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
                (Transaction.date < cursor_date)
                | ((Transaction.date == cursor_date) & (Transaction.id < cursor_id))
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
    db.commit()
    db.refresh(tx)
    logger.info("transaction.created user=%s id=%s amount=%s", user.id, tx.id, tx.amount)
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
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    today = date.today()
    txs = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.type == "expense",
        Transaction.date >= today - timedelta(days=92),
    ).all()
    return dynamic_budget_suggestions(txs)


# ── Summary ───────────────────────────────────────────────────────────────────
@app.get("/summary")
def get_summary(
    month: str | None = None,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id, month).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    summary = monthly_summary(transactions)
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
        duplicate = db.query(Transaction).filter(
            Transaction.user_id == user.id,
            Transaction.source == "sms",
            Transaction.source_ref == parsed["source_ref"],
        ).first()
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
    if ext not in ("csv", "pdf"):
        raise HTTPException(status_code=400, detail="Upload a CSV or PDF statement")
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
            else:
                rows = parse_pdf(content)

            saved_count = 0
            for row in rows:
                # SHA-256 dedup on date+amount+description
                fingerprint = hashlib.sha256(
                    f"{row['date']}{row['amount']}{row['description']}".encode()
                ).hexdigest()
                row["source_ref"] = fingerprint

                duplicate = db.query(Transaction).filter(
                    Transaction.user_id == user.id,
                    Transaction.source == "statement",
                    Transaction.source_ref == fingerprint,
                ).first()
                if not duplicate:
                    db.add(Transaction(user_id=user.id, **row))
                    saved_count += 1

            db.commit()
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

    context = build_advisor_context(transactions, budgets)

    # Load conversation history if continuing a thread
    history = []
    conversation = None
    if payload.conversation_id:
        conversation = db.query(AIConversation).filter(
            AIConversation.id == payload.conversation_id,
            AIConversation.user_id == user.id,
        ).first()
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

    async def event_generator():
        full_reply = []
        try:
            async for token in ai_router.stream(SYSTEM_PROMPT, messages[1:]):
                full_reply.append(token)
                yield f"data: {token}\n\n"
        except Exception as e:
            logger.exception("advisor.stream.error user=%s", user.id)
            yield f"data: [ERROR] {str(e)[:100]}\n\n"
        finally:
            # Persist assistant reply
            if full_reply:
                reply_text = "".join(full_reply)
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
    conv = db.query(AIConversation).filter(
        AIConversation.id == conv_id,
        AIConversation.user_id == user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return sorted(conv.messages, key=lambda m: m.created_at)


# ── Accounts (Multi-Account Support) ─────────────────────────────────────────
@app.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Account).filter(
        Account.user_id == user.id, Account.is_active == True
    ).order_by(Account.name).all()


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


@app.post("/categorize/recategorize")
async def recategorize_uncategorized(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Re-categorize all 'Other' transactions using LLM."""
    txs = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.category == "Other",
    ).limit(50).all()

    if not txs:
        return {"updated": 0}

    batch = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in txs]
    results = await categorize_batch(batch)

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
    logger.info("recategorize user=%s updated=%d of %d", user.id, updated, len(txs))
    return {"updated": updated, "total_checked": len(txs)}


# ── Proactive Insights ───────────────────────────────────────────────────────
@app.get("/insights/proactive", response_model=list[ProactiveInsight])
async def proactive_insights(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    transactions = _tx_query(db, user.id).limit(300).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    return await generate_proactive_insights(transactions, budgets)


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
    log_event(db, user_id=user.id, action="create", resource_type="webhook", resource_id=hook.id,
             ip_address=request.client.host if request.client else None)
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
    log_event(db, user_id=user.id, action="delete", resource_type="webhook", resource_id=webhook_id,
             ip_address=request.client.host if request.client else None)
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
    accounts = db.query(Account).filter(Account.user_id == user.id, Account.is_active == True).all()
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


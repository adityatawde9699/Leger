"""SMS and bank-statement imports: preview and review, job creation, status, retry and cancel."""

import asyncio
import hashlib
import json
import logging
import time
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..db import get_db
from ..helpers import _cloud_ai_allowed, _statement_row_fingerprint
from ..models import Account, ImportJob, Transaction, User
from ..rate_limit import limiter
from ..schemas import ImportJobOut, ImportPreviewOut, SmsParseRequest, SmsWebhookRequest, TransactionOut, UserContext
from ..services.auto_categorizer import categorize_batch
from ..services.categorization_learner import get_user_overrides
from ..services.sms_parser import parse_sms
from ..services.statements import parse_csv, parse_excel, parse_pdf
from ..services.telemetry import record_telemetry
from ..workers.imports import _schedule_import

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── SMS Import ────────────────────────────────────────────────────────────────
def _save_new_sms_transactions(
    db: Session, user_id: str, messages: list[str], device_id: str | None = None,
) -> list[Transaction]:
    """Parse and store SMS messages, skipping any already imported (or repeated in this batch).

    Each insert runs in a savepoint, so a concurrent request that stores the same
    message first only skips that message instead of failing the whole batch.
    """
    saved: list[Transaction] = []
    seen: set[str] = set()
    for message in messages:
        parsed = parse_sms(message)
        if not parsed or parsed["source_ref"] in seen:
            continue
        seen.add(parsed["source_ref"])
        if device_id:
            parsed["notes"] = f"SMS bridge device: {device_id}"
        duplicate = db.query(Transaction.id).filter(
            Transaction.user_id == user_id,
            Transaction.source == "sms",
            Transaction.source_ref == parsed["source_ref"],
        ).first()
        if duplicate:
            continue
        tx = Transaction(user_id=user_id, **parsed)
        try:
            with db.begin_nested():
                db.add(tx)
        except IntegrityError:
            continue
        saved.append(tx)
    db.commit()
    return saved


@router.post("/imports/sms", response_model=list[TransactionOut])
@limiter.limit(settings.import_rate_limit)
async def import_sms(
    request: Request,
    payload: SmsParseRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    saved = []
    pending_txs = _save_new_sms_transactions(db, user.id, payload.messages)

    # ── AI Categorization upgrade pass ────────────────────────────────────────
    # parse_sms uses keyword rules — upgrade with the full 4-tier pipeline.
    if pending_txs:
        try:
            db.flush()  # ensure tx.id is assigned before we reference it
            user_overrides = get_user_overrides(db, user.id)
            batch_input = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in pending_txs]
            ai_results = await categorize_batch(
                batch_input, user_overrides=user_overrides, allow_cloud_ai=_cloud_ai_allowed(db, user.id)
            )
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
            logger.warning("SMS AI categorization pass failed: %s", type(ai_err).__name__)

    for tx in pending_txs:
        db.refresh(tx)
        saved.append(tx)
    logger.info("sms.import user=%s imported=%d", user.id, len(saved))
    return saved


@router.post("/imports/sms/webhook", response_model=list[TransactionOut])
async def import_sms_webhook(
    payload: SmsWebhookRequest,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Receive SMS payloads from an Android companion bridge and reuse the SMS parser."""
    saved = []
    pending_txs = _save_new_sms_transactions(db, user.id, payload.messages, device_id=payload.device_id)

    # ── AI Categorization upgrade pass ────────────────────────────────────────
    if pending_txs:
        try:
            user_overrides = get_user_overrides(db, user.id)
            batch_input = [{"id": tx.id, "description": tx.description, "type": tx.type} for tx in pending_txs]
            ai_results = await categorize_batch(
                batch_input, user_overrides=user_overrides, allow_cloud_ai=_cloud_ai_allowed(db, user.id)
            )
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
            logger.warning("SMS webhook AI categorization pass failed: %s", type(ai_err).__name__)

    for tx in pending_txs:
        db.refresh(tx)
        saved.append(tx)
    logger.info("sms.webhook user=%s imported=%d", user.id, len(saved))
    return saved


# ── Statement Import (async job) ──────────────────────────────────────────────
def _validate_statement_content(content: bytes, ext: str) -> None:
    if not content:
        raise HTTPException(status_code=400, detail="Statement is empty")
    if ext == "pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF statement")
    if ext == "xls" and not content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise HTTPException(status_code=400, detail="Invalid Excel statement")
    if ext == "csv" and b"\x00" in content:
        raise HTTPException(status_code=400, detail="Invalid CSV statement")
    if ext in {"xlsx", "ods"}:
        try:
            with ZipFile(BytesIO(content)) as archive:
                entries = archive.infolist()
                if (len(entries) > 1000 or
                    sum(entry.file_size for entry in entries) > 50 * 1024 * 1024 or
                    any(entry.file_size > 20 * 1024 * 1024 for entry in entries)):
                    raise HTTPException(status_code=413, detail="Statement expands beyond the allowed size")
                names = {entry.filename for entry in entries}
                if ext == "xlsx" and "[Content_Types].xml" not in names:
                    raise HTTPException(status_code=400, detail="Invalid Excel statement")
                if ext == "ods" and "mimetype" not in names:
                    raise HTTPException(status_code=400, detail="Invalid OpenDocument statement")
        except BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Invalid compressed statement") from exc


@router.post("/imports/statement/preview", response_model=ImportPreviewOut)
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
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.max_upload_mb}MB)")
    _validate_statement_content(content, ext)

    if ext == "csv":
        rows = await asyncio.to_thread(parse_csv, content)
    elif ext in ("xls", "xlsx", "ods"):
        rows = await asyncio.to_thread(parse_excel, content, ext)
    else:
        owner = db.get(User, user.id)
        rows = await parse_pdf(content, allow_cloud_ai=bool(owner and owner.cloud_ai_enabled))

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
                    allow_cloud_ai=_cloud_ai_allowed(db, user.id),
                )
            }
        except Exception as ai_err:
            logger.warning("Statement preview AI categorization failed: %s", type(ai_err).__name__)
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


@router.post("/imports/statement", response_model=ImportJobOut, status_code=202)
@limiter.limit(settings.import_rate_limit)
async def import_statement(
    request: Request,
    file: UploadFile = File(...),
    account_id: str | None = Form(default=None),
    excluded_row_fingerprints: str | None = Form(default=None),
    review_overrides: str | None = Form(default=None),
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

    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(status_code=400, detail=f"File too large (max {settings.max_upload_mb}MB)")
    _validate_statement_content(content, ext)

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
    parsed_overrides: dict[str, dict[str, str]] = {}
    if review_overrides:
        try:
            candidate_overrides = json.loads(review_overrides)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Invalid import review overrides") from exc
        if not isinstance(candidate_overrides, dict):
            raise HTTPException(status_code=400, detail="Invalid import review overrides")
        for fingerprint, override in list(candidate_overrides.items())[: settings.max_import_rows]:
            if not isinstance(fingerprint, str) or not isinstance(override, dict):
                continue
            clean: dict[str, str] = {}
            for key in ("category", "merchant_normalized", "type"):
                value = override.get(key)
                if isinstance(value, str) and len(value) <= 128:
                    clean[key] = value
            if clean:
                parsed_overrides[fingerprint] = clean
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
        review_overrides=json.dumps(parsed_overrides),
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    _schedule_import(job.id)
    logger.info("import.started user=%s job=%s", user.id, job.id)
    return job


@router.get("/imports/jobs", response_model=list[ImportJobOut])
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


@router.get("/imports/jobs/{job_id}", response_model=ImportJobOut)
def get_import_job(
    job_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(ImportJob, job_id)
    if not job or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Import job not found")
    return job


@router.post("/imports/jobs/{job_id}/retry", response_model=ImportJobOut)
@limiter.limit(settings.import_rate_limit)
async def retry_import(
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
    _schedule_import(job.id)
    return job


@router.post("/imports/jobs/{job_id}/cancel", response_model=ImportJobOut)
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

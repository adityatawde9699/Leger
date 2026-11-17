"""Statement import worker: parses stored jobs, categorizes and saves rows, and recovers stuck jobs."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import SessionLocal
from ..helpers import (
    _alias_from_map,
    _apply_import_review_overrides,
    _cloud_ai_allowed,
    _get_balance_at,
    _merchant_alias_map,
    _statement_row_fingerprint,
)
from ..models import ImportJob, Transaction, User
from ..schemas import TransactionIn
from ..services.auto_categorizer import categorize_batch
from ..services.categorization_learner import get_user_overrides
from ..services.statements import parse_csv, parse_excel, parse_pdf
from ..services.telemetry import record_telemetry

logger = logging.getLogger("ledger.api")


_BALANCE_CREDIT_TYPES = ("income", "refund", "reimbursement")


def _imported_running_balances(rows: list[dict], prior_balance: Decimal | None) -> list[Decimal | None]:
    """Running balance for each new statement row, in the order given.

    Rows are walked oldest-first, carrying the balance from row to row; a row with a
    bank-reported balance re-anchors the running total. Statements may list newest
    first, so same-day rows are walked in reverse file order when the file descends.
    Rows that don't move the balance (pending, transfers, cash) get None.
    """
    if not rows:
        return []
    descending = rows[0]["date"] > rows[-1]["date"]
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["date"], -i if descending else i))
    balances: list[Decimal | None] = [None] * len(rows)
    cursor = prior_balance
    for i in order:
        row = rows[i]
        if row.get("running_balance") is not None:
            cursor = Decimal(str(row["running_balance"]))
            balances[i] = cursor
            continue
        if cursor is None or row.get("source") == "cash" or row.get("status", "posted") != "posted":
            continue
        if row["type"] in _BALANCE_CREDIT_TYPES:
            cursor = cursor + row["amount"]
        elif row["type"] == "expense":
            cursor = cursor - row["amount"]
        else:
            continue
        balances[i] = cursor
    return balances


def _insert_import_batch(db: Session, batch: list[Transaction]) -> int:
    """Insert imported rows and return how many were stored.

    If another import of the same statement stored some of these rows first, the
    unique (user, source, source_ref) index rejects the batch; retry it row by row
    so only the conflicting rows are skipped.
    """
    if not batch:
        return 0
    try:
        with db.begin_nested():
            db.add_all(batch)
        return len(batch)
    except IntegrityError:
        pass
    saved = 0
    for tx in batch:
        try:
            with db.begin_nested():
                db.add(tx)
            saved += 1
        except IntegrityError:
            continue
    return saved


_CANCEL_POLL_ROWS = 25


def _save_imported_rows(
    worker_db: Session,
    worker_job: ImportJob,
    rows: list[dict],
    review_overrides: dict,
    excluded_fingerprints: set[str],
) -> int | None:
    """Validate, de-duplicate and store parsed rows; return the saved count, or None if cancelled.

    Pure database and CPU work with many round trips, so the worker runs it in a
    thread instead of on the event loop.
    """
    user_id = worker_job.user_id
    account_id = worker_job.account_id
    # User review is authoritative over model/rule inference.
    _apply_import_review_overrides(rows, review_overrides, account_id)

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

    # Work out which rows will actually be inserted, then their running balances.
    to_insert: list[str] = []
    planned: set[str] = set()
    for _, _, _, fingerprint in prepared:
        if fingerprint in existing_refs or fingerprint in planned or fingerprint in excluded_fingerprints:
            continue
        planned.add(fingerprint)
        to_insert.append(fingerprint)
    validated_by_fp = {fp: validated for validated, _, _, fp in prepared}
    balance_by_fp = dict(zip(
        to_insert,
        _imported_running_balances(
            [validated_by_fp[fp] for fp in to_insert],
            _get_balance_at(worker_db, user_id, as_of_date=None),
        ),
        strict=True,
    ))
    saved_count = 0
    seen: set[str] = set()
    batch: list[Transaction] = []
    aliases = _merchant_alias_map(worker_db, user_id)
    position = 0
    for validated, merchant_norm, ai_confidence, fingerprint in prepared:
        # Poll for cancellation every few rows rather than with a query per row.
        position += 1
        cancel_requested = position % _CANCEL_POLL_ROWS == 1 and worker_db.query(
            ImportJob.cancel_requested).filter(ImportJob.id == worker_job.id).scalar()
        if cancel_requested:
            saved_count += _insert_import_batch(worker_db, batch)
            worker_job.status = "cancelled"
            worker_job.cancel_requested = True
            worker_job.row_count = saved_count
            worker_job.processed_rows = min(worker_job.total_rows or 0, saved_count)
            worker_job.error_message = "Import cancelled; already processed rows remain safe and can be retried."
            worker_db.commit()
            return None
        if fingerprint in existing_refs or fingerprint in seen:
            worker_job.processed_rows += 1
            continue
        if fingerprint in excluded_fingerprints:
            worker_job.processed_rows += 1
            continue
        seen.add(fingerprint)
        new_tx = Transaction(user_id=user_id, **validated)
        new_tx.merchant_normalized = _alias_from_map(aliases, new_tx.description, merchant_norm)
        if ai_confidence is not None:
            new_tx.confidence = ai_confidence
        if new_tx.running_balance is None:
            new_tx.running_balance = balance_by_fp.get(fingerprint)
        batch.append(new_tx)
        worker_job.processed_rows += 1
        if len(batch) >= 100:
            saved_count += _insert_import_batch(worker_db, batch)
            batch = []
            worker_db.commit()
    saved_count += _insert_import_batch(worker_db, batch)

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
    return saved_count


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
        try:
            excluded_fingerprints = set(json.loads(worker_job.excluded_row_fingerprints or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            excluded_fingerprints = set()
        try:
            review_overrides = json.loads(worker_job.review_overrides or "{}")
            if not isinstance(review_overrides, dict):
                review_overrides = {}
        except (TypeError, ValueError, json.JSONDecodeError):
            review_overrides = {}
        if ext == "csv":
            rows = await asyncio.to_thread(parse_csv, content)
        elif ext in ("xls", "xlsx", "ods"):
            rows = await asyncio.to_thread(parse_excel, content, ext)
        else:
            owner = worker_db.get(User, worker_job.user_id)
            rows = await parse_pdf(content, allow_cloud_ai=bool(owner and owner.cloud_ai_enabled))

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
                ai_results = await categorize_batch(
                    batch_input, user_overrides=user_overrides,
                    allow_cloud_ai=_cloud_ai_allowed(worker_db, user_id),
                )
                for res in ai_results:
                    idx = int(res["id"])
                    if res.get("confidence", 0) >= 0.6 and res.get("category", "Other") != "Other":
                        rows[idx]["category"] = res["category"]
                        rows[idx]["ai_confidence"] = res["confidence"]
                    if res.get("merchant"):
                        rows[idx]["merchant_normalized"] = res["merchant"]
            except Exception as ai_err:
                logger.warning("Statement AI categorization pass failed: %s", type(ai_err).__name__)

        saved_count = await asyncio.to_thread(
            _save_imported_rows, worker_db, worker_job, rows, review_overrides, excluded_fingerprints,
        )
        if saved_count is None:
            return
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
            # Parser/validation errors describe the user's own file and are safe to show;
            # anything else (database, provider, internal errors) is logged, not returned.
            if isinstance(exc, ValueError):
                worker_job.error_message = str(exc)[:500]
            else:
                logger.exception("import.worker_failed job=%s", job_id)
                worker_job.error_message = "Import failed because of a server error. Please retry the import."
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


def _next_recoverable_import() -> str | None:
    """The next pending job, re-queueing one stuck in processing for 5+ minutes (blocking I/O)."""
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
        return job.id if job else None
    except Exception:
        recovery_db.rollback()
        logger.exception("import.recovery.poll_failed")
        return None
    finally:
        recovery_db.close()


async def _import_recovery_loop() -> None:
    """Recover pending jobs after a process restart."""
    await asyncio.sleep(1)
    while True:
        job_id = await asyncio.to_thread(_next_recoverable_import)
        if job_id:
            await _process_import_job(job_id)
        else:
            await asyncio.sleep(5)


# Strong references keep in-flight import tasks from being garbage-collected mid-run.
_import_tasks: set[asyncio.Task] = set()


def _schedule_import(job_id: str) -> None:
    """Start processing a stored import job on the running event loop."""
    task = asyncio.create_task(_process_import_job(job_id))
    _import_tasks.add(task)
    task.add_done_callback(_import_tasks.discard)

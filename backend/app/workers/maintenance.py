"""Maintenance loop: session and payload cleanup, retention purges and rule-based notifications."""

import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from ..cache import _user_cache_version, llm_cache
from ..config import settings
from ..db import SessionLocal
from ..helpers import _account_currency_mismatch_count, _tx_query
from ..models import AppSession, Budget, ImportJob, Notification, User
from ..services.anomaly_detector import detect_anomalies
from ..services.notification_policy import apply_notification_policy
from ..services.privacy import purge_expired_conversations
from ..services.proactive_insights import apply_insight_frequency, deterministic_proactive_insights

logger = logging.getLogger("ledger.api")


def _purge_stale_import_payloads(db: Session, now: datetime | None = None) -> int:
    """Erase raw statement files from failed/cancelled imports past the retry window.

    Successful imports clear their payload immediately; without this, a failed or
    cancelled job kept the user's full bank statement in the database indefinitely.
    """
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=settings.import_payload_retention_hours)
    purged = db.query(ImportJob).filter(
        ImportJob.status.in_(("failed", "cancelled")),
        ImportJob.file_content.isnot(None),
        ImportJob.updated_at < cutoff,
    ).update({ImportJob.file_content: None}, synchronize_session=False)
    db.commit()
    return purged


def _run_maintenance_cycle() -> None:
    """One pass of maintenance. Database work for every user, so it runs in a thread."""
    db = SessionLocal()
    try:
        db.query(AppSession).filter(AppSession.expires_at < datetime.now(UTC)).delete()
        db.commit()
        if purged := _purge_stale_import_payloads(db):
            logger.info("maintenance.import_payloads_purged count=%d", purged)
        for db_user in db.query(User).all():
            purge_expired_conversations(db, db_user.id, settings.ai_conversation_retention_days)
            if db_user.insight_frequency == "off" or _account_currency_mismatch_count(db, db_user.id):
                continue
            transactions = _tx_query(db, db_user.id).limit(300).all()
            budgets = db.query(Budget).filter(Budget.user_id == db_user.id).all()
            currency = db_user.currency_preference
            deterministic = deterministic_proactive_insights(
                transactions,
                budgets,
                detect_anomalies(transactions, currency),
                currency,
                recurring_tolerance=db_user.recurring_tolerance,
            )
            deterministic = apply_insight_frequency(deterministic, db_user.insight_frequency)
            deterministic = apply_notification_policy(
                deterministic,
                now=datetime.now(UTC),
                start=db_user.quiet_hours_start,
                end=db_user.quiet_hours_end,
                daily_cap=db_user.proactive_daily_cap,
            )
            day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
            already_notified = db.query(Notification.id).filter(
                Notification.user_id == db_user.id,
                Notification.created_at >= day_start,
            ).first()
            if deterministic and not already_notified:
                item = deterministic[0]
                db.add(Notification(
                    user_id=db_user.id,
                    kind="insight",
                    insight_id=item.get("id", "unknown"),
                    text=item.get("text", "Review your latest financial insight."),
                    payload=json.dumps({"priority": item.get("priority", 0), "action": item.get("action")}),
                ))
                db.commit()
            cache_key = f"{db_user.id}:proactive:{_user_cache_version(db, db_user.id)}:{currency}:cloud-0:frequency-{db_user.insight_frequency}"
            llm_cache.put(cache_key, deterministic, ttl=settings.insight_cache_ttl_hours * 3600)
    except Exception:
        db.rollback()
        logger.exception("maintenance.cycle_failed")
    finally:
        db.close()


async def _maintenance_loop() -> None:
    """Run bounded, deterministic maintenance work in a recoverable loop.

    Imports have their own worker (app.workers.imports). This loop refreshes rule-based insight
    cache entries, evaluates recurring observations through that same engine,
    applies notification policy, and purges expired conversations. It never
    calls a cloud provider, so a scheduler failure cannot create AI spend.
    """
    await asyncio.sleep(2)
    while True:
        try:
            await asyncio.to_thread(_run_maintenance_cycle)
        except Exception:
            logger.exception("maintenance.cycle_crashed")
        await asyncio.sleep(300)

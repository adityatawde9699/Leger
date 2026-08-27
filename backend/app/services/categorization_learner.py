"""
Categorization Learner — persists user category corrections and builds
a user-specific override dict for the categorization pipeline.

How it works
------------
1. When a user manually recategorises a transaction the caller invokes
   ``record_correction()``.  The description is hashed (SHA-256 of its
   lowercase, stripped form) and upserted into ``category_corrections``.
2. Before auto-categorizing a new transaction ``get_user_overrides()``
   fetches the full per-user override map (hash → category).
3. During categorization ``apply_user_overrides()`` checks whether the
   incoming description already has a learned override; if so it is
   returned directly, bypassing the rules engine.

The hash-based key means:
- User PII (exact merchant names) is never stored in the corrections table.
- Lookups are O(1) dict membership tests.
- Corrections survive minor whitespace/case variations automatically.
"""

import hashlib
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import CategoryCorrection

logger = logging.getLogger("ledger.cat_learner")


# ── Description normalisation & hashing ──────────────────────────────────────


def _normalise(description: str) -> str:
    """
    Normalise a description for consistent hashing.

    Steps: lowercase → strip surrounding whitespace → collapse inner spaces.
    """
    return " ".join(description.lower().split())


def _hash_description(description: str) -> str:
    """
    Return a SHA-256 hex digest of the normalised description.

    This is the stable key used throughout the corrections table.

    Args:
        description: Raw transaction description string.

    Returns:
        64-character lowercase hex string.
    """
    normalised = _normalise(description)
    return hashlib.sha256(normalised.encode("utf-8")).hexdigest()


# ── Public API ────────────────────────────────────────────────────────────────


def get_user_overrides(db: Session, user_id: str) -> dict[str, str]:
    """
    Return all category overrides for a given user.

    Only corrections with at least one confirmed correction count are returned
    (i.e. every row in the table qualifies, since default correction_count=1).
    Rows are ordered by ``correction_count`` descending so that more
    frequently confirmed overrides naturally dominate if the same hash
    somehow has competing entries (shouldn't happen due to UNIQUE constraint,
    but defensive ordering is free).

    Args:
        db:      SQLAlchemy session.
        user_id: Authenticated user's ID.

    Returns:
        Dict mapping ``description_hash`` → ``category``.
        Empty dict if no corrections exist yet.
    """
    try:
        rows = (
            db.query(CategoryCorrection)
            .filter(
                CategoryCorrection.user_id == user_id,
                CategoryCorrection.correction_count >= 1,
            )
            .order_by(CategoryCorrection.correction_count.desc())
            .all()
        )
        overrides: dict[str, str] = {row.description_hash: row.category for row in rows}
        logger.debug("get_user_overrides: loaded %d overrides for user %s", len(overrides), user_id)
        return overrides
    except Exception:
        logger.exception("get_user_overrides: DB error for user %s — returning empty dict", user_id)
        return {}


def record_correction(
    db: Session,
    user_id: str,
    description: str,
    new_category: str,
) -> None:
    """
    Persist a user's manual category correction.

    If a correction for the same (user, description_hash) pair already
    exists the category is updated and ``correction_count`` is incremented
    by 1.  If it is a new correction a fresh row is inserted.

    Args:
        db:           SQLAlchemy session.
        user_id:      Authenticated user's ID.
        description:  Original transaction description (will be hashed).
        new_category: The category the user selected as correct.

    Raises:
        Does NOT raise — all errors are caught and logged so the caller's
        main categorization flow is never interrupted by a learner failure.
    """
    desc_hash = _hash_description(description)

    try:
        existing = (
            db.query(CategoryCorrection)
            .filter(
                CategoryCorrection.user_id == user_id,
                CategoryCorrection.description_hash == desc_hash,
            )
            .first()
        )

        if existing:
            existing.category = new_category
            existing.correction_count += 1
            logger.info(
                "record_correction: updated override for user=%s hash=%s → '%s' (count=%d)",
                user_id,
                desc_hash[:12],
                new_category,
                existing.correction_count,
            )
        else:
            correction = CategoryCorrection(
                user_id=user_id,
                description_hash=desc_hash,
                category=new_category,
                correction_count=1,
            )
            db.add(correction)
            logger.info(
                "record_correction: new override for user=%s hash=%s → '%s'",
                user_id,
                desc_hash[:12],
                new_category,
            )

        db.commit()

    except IntegrityError:
        # Race condition on the UNIQUE constraint — another request inserted
        # the same row concurrently.  Roll back and re-try the update path.
        db.rollback()
        logger.warning(
            "record_correction: IntegrityError (race) for user=%s hash=%s — attempting update",
            user_id,
            desc_hash[:12],
        )
        try:
            existing = (
                db.query(CategoryCorrection)
                .filter(
                    CategoryCorrection.user_id == user_id,
                    CategoryCorrection.description_hash == desc_hash,
                )
                .first()
            )
            if existing:
                existing.category = new_category
                existing.correction_count += 1
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("record_correction: retry also failed for user=%s hash=%s", user_id, desc_hash[:12])

    except Exception:
        db.rollback()
        logger.exception("record_correction: unexpected error for user=%s hash=%s", user_id, desc_hash[:12])


def apply_user_overrides(
    description: str,
    user_overrides: dict[str, str],
) -> str | None:
    """
    Return the learned category for a description, or None if no override exists.

    This function is designed to be called in the hot path of the
    categorization pipeline.  It is a pure in-memory lookup and performs
    no I/O.

    Args:
        description:    Raw transaction description string.
        user_overrides: Dict returned by ``get_user_overrides()``.

    Returns:
        Category string if an override is found, else None.

    Example::

        overrides = get_user_overrides(db, user_id)
        category = apply_user_overrides(tx.description, overrides)
        if category is None:
            category = categorize(tx.description, tx.type)  # fallback
    """
    if not user_overrides:
        return None
    desc_hash = _hash_description(description)
    return user_overrides.get(desc_hash)


def correction_stats(db: Session, user_id: str) -> dict[str, Any]:
    """
    Return summary statistics about a user's learned corrections.

    Useful for displaying personalisation progress in the UI.

    Args:
        db:      SQLAlchemy session.
        user_id: Authenticated user's ID.

    Returns:
        Dict with:
        - ``total_corrections``   int  — distinct description overrides
        - ``total_confirmations`` int  — sum of all correction_count values
        - ``top_categories``      list[{"category": str, "count": int}]
                                       — most frequently corrected categories
    """
    try:
        rows = db.query(CategoryCorrection).filter(CategoryCorrection.user_id == user_id).all()

        total_corrections = len(rows)
        total_confirmations = sum(r.correction_count for r in rows)

        # Tally per-category override counts
        cat_counts: dict[str, int] = {}
        for row in rows:
            cat_counts[row.category] = cat_counts.get(row.category, 0) + row.correction_count

        top_categories = sorted(
            [{"category": cat, "count": cnt} for cat, cnt in cat_counts.items()],
            key=lambda x: x["count"],
            reverse=True,
        )[:10]

        return {
            "total_corrections": total_corrections,
            "total_confirmations": total_confirmations,
            "top_categories": top_categories,
        }

    except Exception:
        logger.exception("correction_stats: DB error for user=%s — returning empty stats", user_id)
        return {"total_corrections": 0, "total_confirmations": 0, "top_categories": []}

"""Personalization: merchant aliases, custom categories and recurring payment rules."""

import json
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..helpers import _client_ip, _merchant_key, _recurring_payload
from ..models import MerchantAlias, RecurringRule, Transaction, UserCategory
from ..schemas import (
    MerchantAliasIn,
    MerchantAliasOut,
    RecurringRuleIn,
    RecurringRuleOut,
    UserCategoryIn,
    UserCategoryOut,
    UserContext,
)
from ..services.audit import log_event
from ..services.categorizer import CATEGORIES

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Personalization ─────────────────────────────────────────────────────────
@router.get("/merchant-aliases", response_model=list[MerchantAliasOut])
def list_merchant_aliases(user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(MerchantAlias).filter(MerchantAlias.user_id == user.id).order_by(MerchantAlias.alias_key).all()


@router.post("/merchant-aliases", response_model=MerchantAliasOut, status_code=201)
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


@router.delete("/merchant-aliases/{alias_id}")
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


@router.get("/categories", response_model=list[UserCategoryOut])
def list_categories(user: UserContext = Depends(get_current_user), db: Session = Depends(get_db)):
    builtins = [
        _category_payload(name, "income" if name in {"Salary", "Freelance"} else "expense", name,
                          is_custom=False, category_id=f"default:{name}")
        for name in CATEGORIES
    ]
    custom = db.query(UserCategory).filter(UserCategory.user_id == user.id, UserCategory.is_active.is_(True)).order_by(UserCategory.name).all()
    return builtins + [_category_payload(c.name, c.kind, c.reporting_group, is_custom=True, category_id=c.id) for c in custom]


@router.post("/categories", response_model=UserCategoryOut, status_code=201)
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


@router.delete("/categories/{category_id}")
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


@router.get("/recurring", response_model=list[RecurringRuleOut])
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


@router.post("/recurring", response_model=RecurringRuleOut, status_code=201)
def create_recurring_rule(
    payload: RecurringRuleIn,
    request: Request,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    values = payload.model_dump()
    evidence = _validated_evidence_ids(db, user.id, values.pop("evidence_transaction_ids"))
    confirmed = values.get("confirmed", False)
    if confirmed and evidence:
        existing_rules = db.query(RecurringRule).filter(
            RecurringRule.user_id == user.id, RecurringRule.description == values["description"],
            RecurringRule.category == values["category"], RecurringRule.confirmed.is_(True),
        ).all()
        for existing in existing_rules:
            if json.loads(existing.evidence_transaction_ids or "[]") == evidence:
                if existing.average_amount != values["average_amount"] or existing.cadence != values["cadence"]:
                    raise HTTPException(status_code=409, detail="Recurring evidence was already used with different terms")
                return _recurring_payload(existing)
    rule = RecurringRule(user_id=user.id, **values, evidence_transaction_ids=json.dumps(evidence), confirmed_at=datetime.now(UTC) if confirmed else None)
    db.add(rule)
    db.flush()
    log_event(db, user_id=user.id, action="create", resource_type="recurring_rule", resource_id=rule.id, ip_address=_client_ip(request))
    db.commit()
    db.refresh(rule)
    return _recurring_payload(rule)


@router.put("/recurring/{rule_id}", response_model=RecurringRuleOut)
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


@router.delete("/recurring/{rule_id}")
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

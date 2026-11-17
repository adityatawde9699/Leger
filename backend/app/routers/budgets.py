"""Budgets and savings goals, including rule-based budget suggestions."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..db import get_db
from ..helpers import _client_ip, _history_start
from ..models import Budget, Goal, Transaction
from ..schemas import BudgetIn, BudgetOut, GoalIn, GoalOut, UserContext
from ..services.audit import log_event
from ..services.insights import dynamic_budget_suggestions

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Budgets ───────────────────────────────────────────────────────────────────
@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Budget).filter(Budget.user_id == user.id).order_by(Budget.category).all()


# ── Goals ────────────────────────────────────────────────────────────────────
@router.get("/goals", response_model=list[GoalOut])
def list_goals(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Goal).filter(Goal.user_id == user.id).order_by(Goal.status, Goal.deadline, Goal.created_at).all()


@router.post("/goals", response_model=GoalOut, status_code=201)
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


@router.put("/goals/{goal_id}", response_model=GoalOut)
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


@router.delete("/goals/{goal_id}")
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


@router.put("/budgets", response_model=list[BudgetOut])
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


@router.get("/budgets/suggestions")
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

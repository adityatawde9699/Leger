"""Investments: portfolios, holdings, portfolio summary and analytics."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, selectinload

from ..auth import get_current_user
from ..db import get_db
from ..helpers import _client_ip
from ..models import Holding, Portfolio, User
from ..schemas import HoldingIn, HoldingOut, PortfolioIn, PortfolioOut, UserContext
from ..services.audit import log_event
from ..services.portfolio_analytics import compute_portfolio_analytics

router = APIRouter()
logger = logging.getLogger("ledger.api")


# ── Portfolios ────────────────────────────────────────────────────────────────
@router.get("/portfolios", response_model=list[PortfolioOut])
def list_portfolios(
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(Portfolio).filter(Portfolio.user_id == user.id).order_by(Portfolio.created_at.desc()).all()


@router.post("/portfolios", response_model=PortfolioOut, status_code=201)
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


@router.delete("/portfolios/{portfolio_id}")
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
@router.get("/portfolios/{portfolio_id}/holdings", response_model=list[HoldingOut])
def list_holdings(
    portfolio_id: str,
    user: UserContext = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    p = db.get(Portfolio, portfolio_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return p.holdings


@router.post("/portfolios/{portfolio_id}/holdings", response_model=HoldingOut, status_code=201)
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


@router.put("/holdings/{holding_id}", response_model=HoldingOut)
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


@router.delete("/holdings/{holding_id}")
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
@router.get("/portfolios/summary")
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


# ── Portfolio Analytics ───────────────────────────────────────────────────────
@router.get("/portfolios/analytics")
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
        return {"allocation": [], "total_return_pct": 0, "sharpe_ratio": None, "risk_comfort": db.get(User, user.id).risk_comfort}

    holdings_by_portfolio = {p.id: p.holdings for p in portfolios}
    return {
        **compute_portfolio_analytics(portfolios, holdings_by_portfolio),
        "risk_comfort": db.get(User, user.id).risk_comfort,
        "risk_preference_disclosure": "This is a stated preference, not a risk score or investment recommendation.",
    }

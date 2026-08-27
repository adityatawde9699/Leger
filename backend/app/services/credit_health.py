"""
Credit Health Score v2 — upgraded with temporal trend, income stability, and emergency fund proxy.
"""

from collections import defaultdict
from typing import Any


def compute_credit_health(
    transactions: list,
    budgets: list,
    accounts: list | None = None,
) -> dict[str, Any]:
    """
    Compute a financial health score from 300-900.

    Factors (v2):
    - Savings rate (20%)          — higher savings = better
    - Budget adherence (20%)      — staying in budget = better
    - Spending consistency (15%)  — low variance = better
    - Category diversification (10%) — diversified tracking = better
    - Credit utilization proxy (10%) — low credit usage = better
    - Income stability (15%)      — steady income = better [NEW]
    - Savings trend (10%)         — improving trajectory = better [NEW]
    """

    scores = {}

    incomes = [float(t.amount) for t in transactions if t.type == "income"]
    expenses = [float(t.amount) for t in transactions if t.type == "expense"]
    total_income = sum(incomes) or 1
    total_expense = sum(expenses)
    savings_rate = max(0, (total_income - total_expense) / total_income)

    # ── 1. Savings Rate (0-180 points) ────────────────────────────────────────
    if savings_rate >= 0.35:
        savings_score = 180
    elif savings_rate >= 0.25:
        savings_score = 160
    elif savings_rate >= 0.20:
        savings_score = 135
    elif savings_rate >= 0.10:
        savings_score = 100
    elif savings_rate >= 0:
        savings_score = 65
    else:
        savings_score = 30
    scores["savings"] = {"score": savings_score, "max": 180, "rate": round(savings_rate * 100, 1)}

    # ── 2. Budget Adherence (0-180 points) ────────────────────────────────────
    if budgets:
        cat_spent: dict[str, float] = defaultdict(float)
        for t in transactions:
            if t.type == "expense":
                cat_spent[t.category] += float(t.amount)

        adherent = sum(
            1 for b in budgets if float(b.monthly_limit) > 0 and cat_spent.get(b.category, 0) <= float(b.monthly_limit)
        )
        adherence_rate = adherent / len(budgets)
        budget_score = int(180 * adherence_rate)
    else:
        budget_score = 90  # neutral
        adherence_rate = 0.5
    scores["budget_adherence"] = {"score": budget_score, "max": 180, "rate": round(adherence_rate * 100, 1)}

    # ── 3. Spending Consistency (0-135 points) — low CV = good ────────────────
    daily_spend: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.type == "expense":
            daily_spend[str(t.date)] += float(t.amount)

    if len(daily_spend) > 1:
        vals = list(daily_spend.values())
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        cv = (variance**0.5) / mean if mean > 0 else 0
        if cv < 0.3:
            consistency_score = 135
        elif cv < 0.6:
            consistency_score = 105
        elif cv < 1.0:
            consistency_score = 75
        else:
            consistency_score = 45
    else:
        consistency_score = 70
    scores["consistency"] = {"score": consistency_score, "max": 135}

    # ── 4. Category Diversification (0-90 points) ─────────────────────────────
    categories_used = {t.category for t in transactions if t.type == "expense"}
    cat_count = len(categories_used)
    if cat_count >= 8:
        diversity_score = 90
    elif cat_count >= 6:
        diversity_score = 75
    elif cat_count >= 4:
        diversity_score = 55
    elif cat_count >= 2:
        diversity_score = 35
    else:
        diversity_score = 15
    scores["diversity"] = {"score": diversity_score, "max": 90, "categories": cat_count}

    # ── 5. Credit Utilization Proxy (0-90 points) ─────────────────────────────
    if accounts:
        total_balance = sum(float(a.balance) for a in accounts if a.is_active)
        credit_accounts = [a for a in accounts if a.account_type == "credit"]
        if credit_accounts:
            credit_balance = sum(float(a.balance) for a in credit_accounts)
            utilization = abs(credit_balance) / (abs(total_balance) + 1)
            if utilization < 0.2:
                credit_score = 90
            elif utilization < 0.35:
                credit_score = 70
            elif utilization < 0.5:
                credit_score = 45
            else:
                credit_score = 20
        else:
            credit_score = 75  # No credit = generally good
    else:
        credit_score = 60
    scores["credit_utilization"] = {"score": credit_score, "max": 90}

    # ── 6. Income Stability (0-135 points) [NEW] — consistent income = good ────
    monthly_income: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.type == "income":
            month = t.date.strftime("%Y-%m")
            monthly_income[month] += float(t.amount)

    if len(monthly_income) >= 2:
        inc_vals = list(monthly_income.values())
        inc_mean = sum(inc_vals) / len(inc_vals)
        inc_var = sum((v - inc_mean) ** 2 for v in inc_vals) / len(inc_vals)
        inc_cv = (inc_var**0.5) / inc_mean if inc_mean > 0 else 1
        if inc_cv < 0.1:
            income_score = 135
        elif inc_cv < 0.25:
            income_score = 110
        elif inc_cv < 0.5:
            income_score = 80
        else:
            income_score = 45
    else:
        income_score = 70
    scores["income_stability"] = {"score": income_score, "max": 135}

    # ── 7. Savings Trend (0-90 points) [NEW] — improving trajectory = good ─────
    monthly_net: dict[str, float] = defaultdict(float)
    for t in transactions:
        month = t.date.strftime("%Y-%m")
        monthly_net[month] += float(t.amount) if t.type == "income" else -float(t.amount)

    sorted_months = sorted(monthly_net.items())
    if len(sorted_months) >= 3:
        recent_half = sorted_months[len(sorted_months) // 2 :]
        prior_half = sorted_months[: len(sorted_months) // 2]
        recent_avg = sum(v for _, v in recent_half) / len(recent_half)
        prior_avg = sum(v for _, v in prior_half) / len(prior_half)
        if recent_avg > prior_avg * 1.10:
            trend_score = 90
            trend = "improving"
        elif recent_avg > prior_avg * 0.95:
            trend_score = 65
            trend = "stable"
        else:
            trend_score = 30
            trend = "declining"
    else:
        trend_score = 45
        trend = "stable"
    scores["savings_trend"] = {"score": trend_score, "max": 90, "trend": trend}

    # ── Total ──────────────────────────────────────────────────────────────────
    total = sum(s["score"] for s in scores.values())
    total = max(300, min(900, total))

    if total >= 800:
        grade = "Excellent"
        color = "#16a34a"
    elif total >= 700:
        grade = "Very Good"
        color = "#22c55e"
    elif total >= 600:
        grade = "Good"
        color = "#2563eb"
    elif total >= 500:
        grade = "Fair"
        color = "#f59e0b"
    elif total >= 400:
        grade = "Poor"
        color = "#ef4444"
    else:
        grade = "Critical"
        color = "#dc2626"

    # Emergency fund proxy: months of expenses covered by bank balances
    if accounts:
        bank_balances = sum(
            float(a.balance) for a in accounts if a.is_active and a.account_type in ("savings", "current", "wallet")
        )
        avg_monthly_expense = total_expense / max(len({t.date.strftime("%Y-%m") for t in transactions}), 1)
        emergency_months = bank_balances / avg_monthly_expense if avg_monthly_expense > 0 else 0
    else:
        emergency_months = None

    tips = []
    if savings_rate < 0.20:
        tips.append("Save at least 20% of your income — try automating transfers on payday")
    if not budgets:
        tips.append("Set monthly budgets for your top 3 spending categories")
    if cat_count < 5:
        tips.append("Track more expense categories for a complete financial picture")
    if emergency_months is not None and emergency_months < 3:
        tips.append(f"Build an emergency fund — you have ~{emergency_months:.1f} months of expenses saved")
    if trend == "declining":
        tips.append("Your savings trend is declining — review last 3 months' expenses")

    return {
        "score": total,
        "grade": grade,
        "color": color,
        "breakdown": scores,
        "trend": trend,
        "emergency_months": round(emergency_months, 1) if emergency_months is not None else None,
        "tips": tips,
    }

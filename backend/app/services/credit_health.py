"""
Credit health score — computes a financial health score (0-900) based on
spending patterns, savings rate, budget adherence, and debt indicators.
Similar to CIBIL range but based on behavioral data.
"""
from decimal import Decimal
from typing import Any


def compute_credit_health(
    transactions: list,
    budgets: list,
    accounts: list | None = None,
) -> dict[str, Any]:
    """
    Compute a financial health score from 300-900.
    
    Factors:
    - Savings rate (25%)
    - Budget adherence (25%)
    - Spending consistency (20%)
    - Category diversification (15%)
    - Credit utilization proxy (15%)
    """
    scores = {}

    # 1. Savings rate (0-225 points)
    incomes = [float(t.amount) for t in transactions if t.type == "income"]
    expenses = [float(t.amount) for t in transactions if t.type == "expense"]
    total_income = sum(incomes) or 1
    total_expense = sum(expenses)
    savings_rate = max(0, (total_income - total_expense) / total_income)

    if savings_rate >= 0.3:
        savings_score = 225
    elif savings_rate >= 0.2:
        savings_score = 190
    elif savings_rate >= 0.1:
        savings_score = 150
    elif savings_rate >= 0:
        savings_score = 100
    else:
        savings_score = 50  # negative savings
    scores["savings"] = {"score": savings_score, "max": 225, "rate": round(savings_rate * 100, 1)}

    # 2. Budget adherence (0-225 points)
    if budgets:
        from collections import defaultdict
        cat_spent = defaultdict(float)
        for t in transactions:
            if t.type == "expense":
                cat_spent[t.category] += float(t.amount)

        adherent = 0
        for b in budgets:
            limit = float(b.monthly_limit)
            spent = cat_spent.get(b.category, 0)
            if limit > 0 and spent <= limit:
                adherent += 1
        adherence_rate = adherent / len(budgets)
        budget_score = int(225 * adherence_rate)
    else:
        budget_score = 112  # no budgets set = neutral
        adherence_rate = 0.5
    scores["budget_adherence"] = {"score": budget_score, "max": 225, "rate": round(adherence_rate * 100, 1)}

    # 3. Spending consistency (0-180 points) — low variance = good
    from collections import defaultdict
    daily_spend = defaultdict(float)
    for t in transactions:
        if t.type == "expense":
            daily_spend[str(t.date)] += float(t.amount)

    if len(daily_spend) > 1:
        vals = list(daily_spend.values())
        mean = sum(vals) / len(vals)
        variance = sum((v - mean) ** 2 for v in vals) / len(vals)
        cv = (variance ** 0.5) / mean if mean > 0 else 0  # coefficient of variation
        if cv < 0.3:
            consistency_score = 180
        elif cv < 0.6:
            consistency_score = 140
        elif cv < 1.0:
            consistency_score = 100
        else:
            consistency_score = 60
    else:
        consistency_score = 90
    scores["consistency"] = {"score": consistency_score, "max": 180}

    # 4. Category diversification (0-135 points) — diversified spending = good
    categories_used = set(t.category for t in transactions if t.type == "expense")
    cat_count = len(categories_used)
    if cat_count >= 6:
        diversity_score = 135
    elif cat_count >= 4:
        diversity_score = 110
    elif cat_count >= 2:
        diversity_score = 80
    else:
        diversity_score = 45
    scores["diversity"] = {"score": diversity_score, "max": 135, "categories": cat_count}

    # 5. Account health / credit utilization proxy (0-135 points)
    if accounts:
        total_balance = sum(float(a.balance) for a in accounts if a.is_active)
        credit_accounts = [a for a in accounts if a.account_type == "credit"]
        if credit_accounts:
            credit_balance = sum(float(a.balance) for a in credit_accounts)
            utilization = abs(credit_balance) / (total_balance + 1)
            if utilization < 0.3:
                credit_score = 135
            elif utilization < 0.5:
                credit_score = 100
            else:
                credit_score = 60
        else:
            credit_score = 110  # no credit = generally good
    else:
        credit_score = 90
    scores["credit_utilization"] = {"score": credit_score, "max": 135}

    # Total
    total = sum(s["score"] for s in scores.values())
    total = max(300, min(900, total))  # clamp to 300-900

    # Grade
    if total >= 750:
        grade = "Excellent"
        color = "#16a34a"
    elif total >= 650:
        grade = "Good"
        color = "#2563eb"
    elif total >= 500:
        grade = "Fair"
        color = "#f59e0b"
    else:
        grade = "Poor"
        color = "#dc2626"

    # Tips
    tips = []
    if savings_rate < 0.2:
        tips.append("Try to save at least 20% of your income each month")
    if not budgets:
        tips.append("Set budgets for your top spending categories")
    if cat_count < 4:
        tips.append("Track more categories for a complete financial picture")

    return {
        "score": total,
        "grade": grade,
        "color": color,
        "breakdown": scores,
        "tips": tips,
    }

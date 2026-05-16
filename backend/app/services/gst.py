"""
GST-aware categorization — maps transaction categories to Indian GST rates.
Provides automatic GST computation and HSN/SAC code resolution.
"""
from decimal import Decimal
from typing import Any

# Standard GST rates by category
# SAC = Services, HSN = Goods
GST_MAP: dict[str, dict[str, Any]] = {
    "Dining":         {"rate": 5.0,  "sac": "9963",  "label": "Restaurant services"},
    "Groceries":      {"rate": 0.0,  "sac": None,    "label": "Essential food (exempt)"},
    "Transport":      {"rate": 5.0,  "sac": "9964",  "label": "Passenger transport"},
    "Shopping":       {"rate": 18.0, "hsn": "6201",  "label": "General merchandise"},
    "Subscriptions":  {"rate": 18.0, "sac": "9984",  "label": "Digital services"},
    "Health":         {"rate": 5.0,  "sac": "9993",  "label": "Healthcare services"},
    "Utilities":      {"rate": 18.0, "sac": "9969",  "label": "Telecom & utilities"},
    "Entertainment":  {"rate": 28.0, "sac": "9996",  "label": "Amusement & recreation"},
    "Housing":        {"rate": 0.0,  "sac": None,    "label": "Rent (exempt)"},
    "Other":          {"rate": 18.0, "sac": "9997",  "label": "Other services"},
}

# Common merchant-level overrides (some merchants are composition scheme etc.)
MERCHANT_OVERRIDES: dict[str, float] = {
    "swiggy": 5.0,
    "zomato": 5.0,
    "uber": 5.0,
    "ola": 5.0,
    "netflix": 18.0,
    "spotify": 18.0,
    "amazon prime": 18.0,
}


def compute_gst(
    amount: Decimal,
    category: str,
    merchant: str | None = None,
    is_inclusive: bool = True,
) -> dict[str, Any]:
    """
    Compute GST for a transaction.
    
    Args:
        amount: Transaction amount
        category: Category name
        merchant: Optional merchant name for override lookup
        is_inclusive: If True, amount already includes GST (default for Indian retail)
    
    Returns:
        {"gst_rate": float, "gst_amount": Decimal, "base_amount": Decimal, "hsn_code": str|None}
    """
    gst_info = GST_MAP.get(category, GST_MAP["Other"])
    rate = gst_info["rate"]

    # Check merchant override
    if merchant:
        merchant_lower = merchant.lower()
        for key, override_rate in MERCHANT_OVERRIDES.items():
            if key in merchant_lower:
                rate = override_rate
                break

    if rate == 0:
        return {
            "gst_rate": 0.0,
            "gst_amount": Decimal("0"),
            "base_amount": amount,
            "hsn_code": gst_info.get("sac") or gst_info.get("hsn"),
        }

    if is_inclusive:
        # Amount includes GST — back-calculate
        base = amount * Decimal("100") / (Decimal("100") + Decimal(str(rate)))
        gst_amount = amount - base
    else:
        base = amount
        gst_amount = amount * Decimal(str(rate)) / Decimal("100")

    return {
        "gst_rate": rate,
        "gst_amount": round(gst_amount, 2),
        "base_amount": round(base, 2),
        "hsn_code": gst_info.get("sac") or gst_info.get("hsn"),
    }


def generate_gst_report(transactions: list) -> dict[str, Any]:
    """
    Generate a GST summary report from transactions.
    Returns breakdown by slab with totals.
    """
    slabs: dict[float, dict] = {}
    total_gst = Decimal("0")
    total_base = Decimal("0")

    for tx in transactions:
        if tx.type != "expense":
            continue
        gst = compute_gst(tx.amount, tx.category, tx.merchant_normalized)
        rate = gst["gst_rate"]
        if rate not in slabs:
            slabs[rate] = {"rate": rate, "count": 0, "base_total": Decimal("0"), "gst_total": Decimal("0")}
        slabs[rate]["count"] += 1
        slabs[rate]["base_total"] += gst["base_amount"]
        slabs[rate]["gst_total"] += gst["gst_amount"]
        total_gst += gst["gst_amount"]
        total_base += gst["base_amount"]

    return {
        "slabs": sorted(slabs.values(), key=lambda s: s["rate"]),
        "total_base": round(total_base, 2),
        "total_gst": round(total_gst, 2),
        "total_with_gst": round(total_base + total_gst, 2),
    }

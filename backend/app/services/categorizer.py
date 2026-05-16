CATEGORIES = [
    "Housing",
    "Groceries",
    "Transport",
    "Dining",
    "Subscriptions",
    "Shopping",
    "Health",
    "Utilities",
    "Entertainment",
    "Other",
    "Salary",
    "Freelance",
]

EXPENSE_CATEGORIES = [c for c in CATEGORIES if c not in {"Salary", "Freelance"}]

RULES: list[tuple[str, str]] = [
    ("swiggy", "Dining"),
    ("zomato", "Dining"),
    ("restaurant", "Dining"),
    ("uber", "Transport"),
    ("ola", "Transport"),
    ("rapido", "Transport"),
    ("amazon", "Shopping"),
    ("flipkart", "Shopping"),
    ("myntra", "Shopping"),
    ("netflix", "Subscriptions"),
    ("spotify", "Subscriptions"),
    ("hotstar", "Subscriptions"),
    ("rent", "Housing"),
    ("electricity", "Utilities"),
    ("airtel", "Utilities"),
    ("jio", "Utilities"),
    ("pharmacy", "Health"),
    ("hospital", "Health"),
    ("salary", "Salary"),
    ("payroll", "Salary"),
]


def categorize(description: str, tx_type: str = "expense") -> str:
    text = description.lower()
    for needle, category in RULES:
        if needle in text:
            return category
    return "Other" if tx_type == "expense" else "Salary"


import re

# ── Category Registry (expanded from 12 → 18) ────────────────────────────────
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
    "Education",
    "Insurance",
    "Investments",
    "Transfers",
    "Taxes",
    "Fees",
    "Other",
    # Income categories
    "Salary",
    "Freelance",
]

EXPENSE_CATEGORIES = [c for c in CATEGORIES if c not in {"Salary", "Freelance"}]
INCOME_CATEGORIES = ["Salary", "Freelance", "Other"]

# ── Rules: (needle, category) — ordered by priority (most specific first) ────
# Format: exact substring match (case-insensitive). Longer/more-specific rules first.
RULES: list[tuple[str, str]] = [
    # ── Income / Salary ───────────────────────────────────────────────────────
    ("salary", "Salary"),
    ("payroll", "Salary"),
    ("ctc", "Salary"),
    ("stipend", "Salary"),
    ("freelance", "Freelance"),
    ("upwork", "Freelance"),
    ("fiverr", "Freelance"),
    ("toptal", "Freelance"),
    # ── Investments ──────────────────────────────────────────────────────────
    ("zerodha", "Investments"),
    ("groww", "Investments"),
    ("kuvera", "Investments"),
    ("coin", "Investments"),
    ("nse", "Investments"),
    ("bse", "Investments"),
    ("ipo", "Investments"),
    ("mutual fund", "Investments"),
    ("sip", "Investments"),
    ("demat", "Investments"),
    ("smallcase", "Investments"),
    ("angel one", "Investments"),
    ("angel broking", "Investments"),
    ("dhan", "Investments"),
    ("5paisa", "Investments"),
    ("upstox", "Investments"),
    ("fyers", "Investments"),
    ("motilaloswal", "Investments"),
    ("icicidirect", "Investments"),
    ("hdfc securit", "Investments"),
    ("sbisec", "Investments"),
    # ── Insurance ────────────────────────────────────────────────────────────
    ("insurance", "Insurance"),
    ("lic ", "Insurance"),
    ("policybazaar", "Insurance"),
    ("premium", "Insurance"),
    ("term plan", "Insurance"),
    ("health insur", "Insurance"),
    ("bajaj allianz", "Insurance"),
    ("star health", "Insurance"),
    ("hdfc life", "Insurance"),
    ("icici lombard", "Insurance"),
    ("new india assu", "Insurance"),
    ("tata aig", "Insurance"),
    ("niva bupa", "Insurance"),
    # ── Taxes ────────────────────────────────────────────────────────────────
    ("income tax", "Taxes"),
    ("tds", "Taxes"),
    ("gst", "Taxes"),
    ("advance tax", "Taxes"),
    ("nsdl", "Taxes"),
    ("traces", "Taxes"),
    ("itr", "Taxes"),
    # ── Transfers ─────────────────────────────────────────────────────────────
    ("neft", "Transfers"),
    ("rtgs", "Transfers"),
    ("imps", "Transfers"),
    ("self transfer", "Transfers"),
    ("own account", "Transfers"),
    # ── Fees & Charges ─────────────────────────────────────────────────────────
    ("bank charge", "Fees"),
    ("processing fee", "Fees"),
    ("annual fee", "Fees"),
    ("late fee", "Fees"),
    ("penalty", "Fees"),
    ("bank fee", "Fees"),
    ("service charge", "Fees"),
    ("atm charge", "Fees"),
    ("convenience fee", "Fees"),
    # ── Education ─────────────────────────────────────────────────────────────
    ("college", "Education"),
    ("university", "Education"),
    ("school", "Education"),
    ("tuition", "Education"),
    ("udemy", "Education"),
    ("coursera", "Education"),
    ("byju", "Education"),
    ("unacademy", "Education"),
    ("vedantu", "Education"),
    ("toppr", "Education"),
    ("khan academy", "Education"),
    ("edx", "Education"),
    ("skillshare", "Education"),
    ("duolingo", "Education"),
    ("exam fee", "Education"),
    ("books", "Education"),
    ("stationery", "Education"),
    # ── Utilities ─────────────────────────────────────────────────────────────
    ("electricity", "Utilities"),
    ("airtel", "Utilities"),
    ("jio", "Utilities"),
    ("bsnl", "Utilities"),
    ("broadband", "Utilities"),
    ("recharge", "Utilities"),
    ("rech", "Utilities"),
    ("vi p", "Utilities"),
    ("billpay", "Utilities"),
    ("utility", "Utilities"),
    ("utilities", "Utilities"),
    ("dth", "Utilities"),
    ("water bill", "Utilities"),
    ("gas bill", "Utilities"),
    ("ebzauranga", "Utilities"),
    ("tata sky", "Utilities"),
    ("dish tv", "Utilities"),
    ("sun direct", "Utilities"),
    ("mahadiscom", "Utilities"),
    ("bescom", "Utilities"),
    ("tpddl", "Utilities"),
    ("msedcl", "Utilities"),
    ("piped gas", "Utilities"),
    ("indane", "Utilities"),
    ("mahanagar gas", "Utilities"),
    # ── Subscriptions ─────────────────────────────────────────────────────────
    ("netflix", "Subscriptions"),
    ("spotify", "Subscriptions"),
    ("hotstar", "Subscriptions"),
    ("prime video", "Subscriptions"),
    ("googleclou", "Subscriptions"),
    ("google cloud", "Subscriptions"),
    ("playstore", "Subscriptions"),
    ("dashreels", "Subscriptions"),
    ("github", "Subscriptions"),
    ("cursor", "Subscriptions"),
    ("youtube", "Subscriptions"),
    ("zee5", "Subscriptions"),
    ("sonyliv", "Subscriptions"),
    ("jiocinema", "Subscriptions"),
    ("mx player", "Subscriptions"),
    ("apple music", "Subscriptions"),
    ("gaana", "Subscriptions"),
    ("jiosaavn", "Subscriptions"),
    ("microsoft 365", "Subscriptions"),
    ("adobe", "Subscriptions"),
    ("canva", "Subscriptions"),
    ("notion", "Subscriptions"),
    ("slack", "Subscriptions"),
    ("zoom", "Subscriptions"),
    ("aws", "Subscriptions"),
    ("azure", "Subscriptions"),
    ("cloudflare", "Subscriptions"),
    ("vercel", "Subscriptions"),
    ("figma", "Subscriptions"),
    # ── Transport ─────────────────────────────────────────────────────────────
    ("uber", "Transport"),
    ("ola", "Transport"),
    ("rapido", "Transport"),
    ("metro", "Transport"),
    ("petrol", "Transport"),
    ("chalo", "Transport"),
    ("irctc", "Transport"),
    ("confirmtkt", "Transport"),
    ("confirm tkt", "Transport"),
    ("railway", "Transport"),
    ("flight", "Transport"),
    ("cab", "Transport"),
    ("auto", "Transport"),
    ("toll", "Transport"),
    ("fastag", "Transport"),
    ("bus", "Transport"),
    ("train", "Transport"),
    ("travel", "Transport"),
    ("indian r", "Transport"),
    ("indigo", "Transport"),
    ("spicejet", "Transport"),
    ("air india", "Transport"),
    ("makemytrip", "Transport"),
    ("goibibo", "Transport"),
    ("cleartrip", "Transport"),
    ("redbus", "Transport"),
    ("paytm travel", "Transport"),
    ("park+", "Transport"),
    ("parkplus", "Transport"),
    ("diesel", "Transport"),
    # ── Health ────────────────────────────────────────────────────────────────
    ("pharmacy", "Health"),
    ("medical", "Health"),
    ("hospital", "Health"),
    ("clinic", "Health"),
    ("dental", "Health"),
    ("doctor", "Health"),
    ("medicine", "Health"),
    ("druggist", "Health"),
    ("chemist", "Health"),
    ("wellness", "Health"),
    ("healthcare", "Health"),
    ("tata 1mg", "Health"),
    ("apollo pharm", "Health"),
    ("pharmeasy", "Health"),
    ("netmeds", "Health"),
    ("cult.fit", "Health"),
    ("cult fit", "Health"),
    ("gym", "Health"),
    ("yoga", "Health"),
    # ── Dining ────────────────────────────────────────────────────────────────
    ("swiggy", "Dining"),
    ("zomato", "Dining"),
    ("restaurant", "Dining"),
    ("cafe", "Dining"),
    ("hotel", "Dining"),
    ("domino", "Dining"),
    ("dimono", "Dining"),
    ("pizza", "Dining"),
    ("mcdonald", "Dining"),
    ("mc donalds", "Dining"),
    ("kfc", "Dining"),
    ("burger king", "Dining"),
    ("burger k", "Dining"),
    ("subway", "Dining"),
    ("starbucks", "Dining"),
    ("dunkin", "Dining"),
    ("sf food", "Dining"),
    ("sana fat", "Dining"),
    ("shiraaz", "Dining"),
    ("koyla", "Dining"),
    ("aarambh", "Dining"),
    ("treat me", "Dining"),
    ("cool bev", "Dining"),
    ("orange j", "Dining"),
    ("roll n r", "Dining"),
    ("raps bir", "Dining"),
    ("bakery", "Dining"),
    ("sweets", "Dining"),
    ("dhaba", "Dining"),
    ("kitchen", "Dining"),
    ("caterers", "Dining"),
    ("kabab", "Dining"),
    ("eats", "Dining"),
    ("bites", "Dining"),
    ("food", "Dining"),
    ("lucky juice", "Dining"),
    ("dosa plaza", "Dining"),
    ("bholes r", "Dining"),
    ("bholes restaurant", "Dining"),
    ("tirupati", "Dining"),
    ("gaavaran", "Dining"),
    ("saikripa", "Dining"),
    ("maa durg", "Dining"),
    ("shree sa", "Dining"),
    ("shri swa", "Dining"),
    ("kalyani", "Dining"),
    ("jijau me", "Dining"),
    ("suprassa", "Dining"),
    ("mess", "Dining"),
    ("canteen", "Dining"),
    ("cateen", "Dining"),
    ("mgm spor", "Dining"),
    ("gajanan", "Dining"),
    ("biryani", "Dining"),
    ("haldiram", "Dining"),
    ("barbeque", "Dining"),
    ("barbeque nation", "Dining"),
    ("chai point", "Dining"),
    ("chaayos", "Dining"),
    ("box8", "Dining"),
    ("faasos", "Dining"),
    ("freshmenu", "Dining"),
    # ── Groceries ─────────────────────────────────────────────────────────────
    ("blinkit", "Groceries"),
    ("zepto", "Groceries"),
    ("instamart", "Groceries"),
    ("dunzo", "Groceries"),
    ("dmart", "Groceries"),
    ("reliance fresh", "Groceries"),
    ("bigbasket", "Groceries"),
    ("milk", "Groceries"),
    ("dairy", "Groceries"),
    ("groceries", "Groceries"),
    ("grocery", "Groceries"),
    ("supermarket", "Groceries"),
    ("mart", "Groceries"),
    ("neel kir", "Groceries"),
    ("tarte ki", "Groceries"),
    ("shree ga", "Groceries"),
    ("kirana", "Groceries"),
    ("nature's basket", "Groceries"),
    ("nature basket", "Groceries"),
    ("smart bazaar", "Groceries"),
    ("more megastore", "Groceries"),
    ("easyday", "Groceries"),
    ("spencers", "Groceries"),
    # ── Entertainment ─────────────────────────────────────────────────────────
    ("movie", "Entertainment"),
    ("bookmyshow", "Entertainment"),
    ("district", "Entertainment"),
    ("sports", "Entertainment"),
    ("cinema", "Entertainment"),
    ("theater", "Entertainment"),
    ("insider", "Entertainment"),
    ("pvr", "Entertainment"),
    ("inox", "Entertainment"),
    ("carnival", "Entertainment"),
    ("amusement", "Entertainment"),
    ("theme park", "Entertainment"),
    ("gaming", "Entertainment"),
    ("steam", "Entertainment"),
    ("playstation", "Entertainment"),
    ("xbox", "Entertainment"),
    ("nintendo", "Entertainment"),
    # ── Housing ───────────────────────────────────────────────────────────────
    ("rent", "Housing"),
    ("maintenance", "Housing"),
    ("society", "Housing"),
    ("flat", "Housing"),
    ("apartment", "Housing"),
    ("housing", "Housing"),
    ("landlord", "Housing"),
    # ── Shopping ──────────────────────────────────────────────────────────────
    ("amazon", "Shopping"),
    ("flipkart", "Shopping"),
    ("myntra", "Shopping"),
    ("croma", "Shopping"),
    ("mr diy", "Shopping"),
    ("ekart", "Shopping"),
    ("shopping", "Shopping"),
    ("clothing", "Shopping"),
    ("dress", "Shopping"),
    ("mall", "Shopping"),
    ("fashion", "Shopping"),
    ("boutique", "Shopping"),
    ("retail", "Shopping"),
    ("footwear", "Shopping"),
    ("shoes", "Shopping"),
    ("prozone", "Shopping"),
    ("samsung", "Shopping"),
    ("saketboo", "Shopping"),
    ("appaji k", "Shopping"),
    ("amazonpayr", "Shopping"),
    ("a mazonpayr", "Shopping"),
    ("nykaa", "Shopping"),
    ("meesho", "Shopping"),
    ("snapdeal", "Shopping"),
    ("ajio", "Shopping"),
    ("tatacliq", "Shopping"),
    ("reliance digit", "Shopping"),
    ("vijay sales", "Shopping"),
    ("decathlon", "Shopping"),
    ("ikea", "Shopping"),
    ("urban ladder", "Shopping"),
    ("pepperfry", "Shopping"),
]

# ── Regex patterns for UPI IDs ─────────────────────────────────────────────────
UPI_GENERIC_RE = re.compile(r"\b(upi|ybl|oksbi|okaxis|okhdfcbank|paytm|gpay|phonepe|bhim)\b", re.I)
UPI_MERCHANT_RE = re.compile(r"UPI/(?:DR|CR)/[^/]+/([^/]+)", re.I)
# Matches merchant in "To MERCHANT via" or "From MERCHANT via" patterns
VIA_MERCHANT_RE = re.compile(r"(?:To|From)\s+([A-Za-z][A-Za-z0-9\s&'.]+?)\s+via", re.I)
# NEFT/RTGS: "NEFT MERCHANT NAME" after the bank code
NEFT_MERCHANT_RE = re.compile(r"(?:NEFT|RTGS|IMPS)[/-]?[A-Z0-9]*/([^/]{3,40})", re.I)


def extract_upi_merchant(description: str) -> str | None:
    """Try multiple patterns to extract merchant name from bank description."""
    text = description or ""

    # Pattern 1: UPI/DR/123/MERCHANT
    m = UPI_MERCHANT_RE.search(text)
    if m:
        merchant = re.sub(r"\s+", " ", m.group(1)).strip(" -/")
        if merchant:
            return merchant

    # Pattern 2: "To MERCHANT via PhonePe/GooglePay"
    m = VIA_MERCHANT_RE.search(text)
    if m:
        merchant = m.group(1).strip()
        if len(merchant) >= 3:
            return merchant

    # Pattern 3: NEFT/merchant name
    m = NEFT_MERCHANT_RE.search(text)
    if m:
        merchant = m.group(1).strip()
        if len(merchant) >= 3:
            return merchant

    return None


def is_generic_upi(description: str, category: str) -> bool:
    """True if description is a generic UPI transaction that the rules couldn't classify."""
    text = description or ""
    merchant = extract_upi_merchant(text)
    return category == "Other" and bool(UPI_GENERIC_RE.search(text) or merchant)


def categorize(description: str, tx_type: str = "expense") -> str:
    """
    Multi-pass rule-based categorizer.

    Pass 1: Exact substring match (most specific)
    Pass 2: Spaceless substring match for 5+ char needles
    Pass 3: Regex UPI merchant extraction + re-run rules on extracted name

    Returns category string; falls back to "Other" (expense) or "Salary" (income).
    """
    text = (description or "").lower()

    # Pass 1: standard substring
    for needle, category in RULES:
        if needle in text:
            return category

    # Pass 2: spaceless match for longer needles
    spaceless_text = text.replace(" ", "")
    for needle, category in RULES:
        needle_spaceless = needle.replace(" ", "")
        if len(needle_spaceless) >= 5 and needle_spaceless in spaceless_text:
            return category

    # Pass 3: extract merchant and re-run rules on it
    merchant = extract_upi_merchant(description)
    if merchant:
        merchant_text = merchant.lower()
        for needle, category in RULES:
            if needle in merchant_text:
                return category
        # Spaceless on merchant too
        merchant_spaceless = merchant_text.replace(" ", "")
        for needle, category in RULES:
            needle_spaceless = needle.replace(" ", "")
            if len(needle_spaceless) >= 4 and needle_spaceless in merchant_spaceless:
                return category

    return "Other" if tx_type == "expense" else "Salary"

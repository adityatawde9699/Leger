from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

# ── Auth ─────────────────────────────────────────────────────────────────────


class UserContext(BaseModel):
    id: str
    email: str | None = None


# ── Profile ───────────────────────────────────────────────────────────────────


class UserProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    currency_preference: str = Field(default="INR", pattern="^[A-Z]{3}$")


class UserProfileOut(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    currency_preference: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileStatsOut(BaseModel):
    total_transactions: int
    total_income: Decimal
    total_expenses: Decimal
    net_balance: Decimal
    accounts_count: int
    budgets_count: int


# ── Accounts ─────────────────────────────────────────────────────────────────


class AccountIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    account_type: str = Field(pattern="^(savings|current|credit|wallet|cash)$")
    institution: str | None = None
    balance: Decimal = Decimal("0")
    currency: str = "INR"


class AccountOut(AccountIn):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Transactions ─────────────────────────────────────────────────────────────


class TransactionIn(BaseModel):
    date: date
    type: str = Field(pattern="^(income|expense)$")
    category: str
    amount: Decimal = Field(gt=0)
    description: str = Field(min_length=1, max_length=500)
    source: str = "cash"
    source_ref: str | None = None
    account_id: str | None = None
    tags: str | None = None
    notes: str | None = None
    running_balance: Decimal | None = None  # Bank balance after this transaction
    stmt_seq: int | None = None  # Row index in bank statement (0-based)


class TransactionOut(BaseModel):
    id: str
    date: date
    type: str
    category: str
    amount: Decimal
    description: str
    merchant_normalized: str | None = None
    source: str
    source_ref: str | None = None
    confidence: float | None = None
    account_id: str | None = None
    tags: str | None = None
    notes: str | None = None
    running_balance: Decimal | None = None  # Bank balance after this transaction
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedTransactions(BaseModel):
    items: list[TransactionOut]
    next_cursor: str | None
    has_more: bool
    total_returned: int


class BulkDeleteRequest(BaseModel):
    transaction_ids: list[str]


# ── Budgets ───────────────────────────────────────────────────────────────────


class BudgetIn(BaseModel):
    category: str
    monthly_limit: Decimal = Field(ge=0)
    strategy: str = "manual"


class BudgetOut(BudgetIn):
    id: str
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Imports ───────────────────────────────────────────────────────────────────


class SmsParseRequest(BaseModel):
    messages: list[str] = Field(min_length=1, max_length=100)


class SmsWebhookRequest(SmsParseRequest):
    device_id: str | None = Field(default=None, max_length=128)
    received_at: datetime | None = None


class ImportJobOut(BaseModel):
    id: str
    status: str
    file_name: str
    row_count: int | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── AI Advisor ────────────────────────────────────────────────────────────────


class AdvisorRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Auto-categorize ──────────────────────────────────────────────────────────


class CategorizeSingleRequest(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    tx_type: str = "expense"


class CategorizeSingleResponse(BaseModel):
    category: str
    confidence: float
    merchant: str | None
    source: str


class CategorizeBatchRequest(BaseModel):
    transactions: list[dict[str, str]] = Field(min_length=1, max_length=50)


# ── Proactive Insights ───────────────────────────────────────────────────────


class ProactiveInsight(BaseModel):
    type: str  # warning | tip | positive | info
    text: str


# ── Receipt ──────────────────────────────────────────────────────────────────


class ReceiptResult(BaseModel):
    description: str
    amount: Decimal
    category: str
    date: date
    type: str = "expense"
    merchant_normalized: str | None = None
    items: list[dict[str, Any]] = []
    confidence: float | None = None


# ── Summary ───────────────────────────────────────────────────────────────────


class SummaryOut(BaseModel):
    income: Decimal
    expenses: Decimal
    net: Decimal
    by_category: dict[str, Any]
    by_day: dict[str, Any]
    insights: list[str]
    recurring: list[dict[str, Any]]


# ── Audit Log ─────────────────────────────────────────────────────────────────


class AuditLogOut(BaseModel):
    id: str
    action: str
    resource_type: str
    resource_id: str | None
    details: str | None
    ip_address: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Webhooks ──────────────────────────────────────────────────────────────────


class WebhookIn(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    events: str = Field(min_length=1, max_length=512)  # comma-separated event names
    secret: str = Field(min_length=16, max_length=64)


class WebhookOut(BaseModel):
    id: str
    url: str
    events: str
    is_active: bool
    last_triggered: datetime | None
    failure_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── GST Report ────────────────────────────────────────────────────────────────


class GSTSlabOut(BaseModel):
    rate: float
    count: int
    base_total: Decimal
    gst_total: Decimal


class GSTReportOut(BaseModel):
    slabs: list[GSTSlabOut]
    total_base: Decimal
    total_gst: Decimal
    total_with_gst: Decimal


# ── Portfolio ─────────────────────────────────────────────────────────────────


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    portfolio_type: str = Field(pattern="^(stocks|mutual_funds|crypto|fixed_deposit|gold)$")


class PortfolioOut(PortfolioIn):
    id: str
    created_at: datetime
    model_config = {"from_attributes": True}


class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=128)
    quantity: Decimal = Field(gt=0)
    buy_price: Decimal = Field(ge=0)
    current_price: Decimal = Field(ge=0, default=Decimal("0"))
    asset_type: str = Field(pattern="^(equity|mf|etf|crypto|fd|gold)$")
    purchase_date: date | None = None
    notes: str | None = None


class HoldingOut(HoldingIn):
    id: str
    portfolio_id: str
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}


# ── Credit Health ─────────────────────────────────────────────────────────────


class CreditHealthOut(BaseModel):
    score: int
    grade: str
    color: str
    breakdown: dict[str, Any]
    tips: list[str]


# ── Benchmarks ────────────────────────────────────────────────────────────────


class BenchmarkCategory(BaseModel):
    category: str
    your_spend: float
    percentile: int
    status: str
    label: str
    benchmark_median: int
    benchmark_p75: int


class BenchmarkOut(BaseModel):
    overall_percentile: int
    total_spending: float
    benchmark_median: int
    categories: list[BenchmarkCategory]
    sample_size: str
    methodology: str

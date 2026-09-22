from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator

# ── Auth ─────────────────────────────────────────────────────────────────────


class UserContext(BaseModel):
    id: str
    email: str | None = None
    name: str | None = None
    picture: str | None = None


# ── Profile ───────────────────────────────────────────────────────────────────


class UserProfileIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    avatar_url: str | None = None
    currency_preference: str = Field(default="INR", pattern="^[A-Z]{3}$")


class DataDeletionRequest(BaseModel):
    confirmation: str = Field(pattern="^DELETE$", description="Type DELETE to permanently erase account data")


class UserProfileOut(BaseModel):
    id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None
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
    last_reconciled_at: datetime | None = None
    last_reconciled_balance: Decimal | None = None
    reconciliation_note: str | None = None

    model_config = {"from_attributes": True}


class ReconciliationRequest(BaseModel):
    observed_balance: Decimal
    note: str | None = Field(default=None, max_length=500)


class ReconciliationOut(BaseModel):
    account_id: str
    previous_balance: Decimal
    observed_balance: Decimal
    difference: Decimal
    reconciled_at: datetime
    note: str | None = None


# ── Transactions ─────────────────────────────────────────────────────────────


class TransactionIn(BaseModel):
    date: date
    type: str = Field(pattern="^(income|expense|refund|reimbursement|transfer)$")
    status: str = Field(default="posted", pattern="^(posted|pending|excluded)$")
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
    status: str = "posted"
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


class MerchantAliasIn(BaseModel):
    alias: str = Field(min_length=1, max_length=128)
    canonical: str = Field(min_length=1, max_length=128)


class MerchantAliasOut(BaseModel):
    id: str
    alias_key: str
    canonical: str
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    kind: str = Field(default="expense", pattern="^(expense|income)$")
    reporting_group: str = Field(default="Other", min_length=1, max_length=64)


class UserCategoryOut(UserCategoryIn):
    id: str
    is_active: bool
    is_custom: bool = True


class RecurringRuleIn(BaseModel):
    description: str = Field(min_length=1, max_length=128)
    category: str = Field(min_length=1, max_length=64)
    cadence: str = Field(pattern="^(weekly|biweekly|monthly|quarterly|irregular)$")
    average_amount: Decimal = Field(gt=0)
    minimum_amount: Decimal = Field(gt=0)
    maximum_amount: Decimal = Field(gt=0)
    next_expected: date | None = None
    confidence: float = Field(ge=0, le=1)
    status: str = Field(default="active", pattern="^(active|paused|cancelled)$")
    confirmed: bool = False
    evidence_transaction_ids: list[str] = Field(default_factory=list, max_length=50)


class RecurringRuleOut(RecurringRuleIn):
    id: str
    confirmed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Goals ────────────────────────────────────────────────────────────────────


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    goal_type: str = Field(default="custom", pattern="^(emergency_fund|debt_payoff|savings|spending_reduction|custom)$")
    target_amount: Decimal = Field(gt=0)
    current_amount: Decimal = Field(default=Decimal("0"), ge=0)
    deadline: date | None = None
    status: str = Field(default="active", pattern="^(active|paused|completed)$")


class GoalOut(GoalIn):
    id: str
    created_at: datetime
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
    file_fingerprint: str | None = None
    total_rows: int | None = None
    processed_rows: int = 0
    cancel_requested: bool = False
    excluded_row_fingerprints: str | None = None
    row_count: int | None = None
    error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ImportPreviewOut(BaseModel):
    file_name: str
    row_count: int
    duplicate_count: int = 0
    preview: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


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
    id: str = ""
    type: str  # warning | tip | positive | info
    text: str
    priority: int = Field(default=2, ge=1, le=5)
    category: str | None = None
    confidence: str = "medium"  # high | medium | low
    source: str = "rules"  # rules | ai
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    action: str | None = None
    action_type: str | None = None
    data_quality: dict[str, Any] = Field(default_factory=dict)


class InsightFeedbackRequest(BaseModel):
    insight_id: str = Field(min_length=1, max_length=256)
    feedback: str = Field(pattern="^(helpful|inaccurate|irrelevant|too_generic|unsafe|completed_action|dismissed|snoozed)$")
    note: str | None = Field(default=None, max_length=300)


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
    data_quality: dict[str, Any] = Field(default_factory=dict)
    analysis: dict[str, Any] = Field(default_factory=dict)


class ScenarioRequest(BaseModel):
    category: str | None = Field(default=None, max_length=128)
    reduction_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    income_change_pct: Decimal = Field(default=Decimal("0"), ge=-100, le=100)
    one_time_expense: Decimal = Field(default=Decimal("0"), ge=0)
    horizon_months: int = Field(default=1, ge=1, le=12)


class ScenarioOut(BaseModel):
    category: str | None
    reduction_pct: Decimal
    income_change_pct: Decimal
    one_time_expense: Decimal
    horizon_months: int
    period_start: date | None
    period_end: date | None
    months_observed: int
    transaction_count: int
    baseline_monthly_income: Decimal
    baseline_monthly_expenses: Decimal
    baseline_monthly_net: Decimal
    category_monthly_spend: Decimal
    monthly_savings: Decimal
    projected_monthly_income: Decimal
    projected_monthly_expenses: Decimal
    projected_monthly_net: Decimal
    first_month_net_after_one_time: Decimal
    horizon_net_change: Decimal
    data_quality: dict[str, Any] = Field(default_factory=dict)


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

    @field_validator("url")
    @classmethod
    def _url_is_absolute_http(cls, v: str) -> str:
        # Cheap, no-DNS shape check; the SSRF (IP-resolution) check runs in the
        # endpoint via url_guard.validate_webhook_url.
        parsed = urlparse(v)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("url must be an absolute http(s) URL")
        return v


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

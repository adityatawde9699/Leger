"""Cross-user probes for resource reads, mutations, downloads and retries."""
from datetime import date
from decimal import Decimal

from app.auth import get_current_user
from app.models import (
    Account,
    AIConversation,
    Goal,
    Holding,
    ImportJob,
    MerchantAlias,
    Notification,
    Portfolio,
    ReceiptAttachment,
    RecurringRule,
    Transaction,
    User,
    UserCategory,
    Webhook,
)
from app.schemas import UserContext

from .conftest import TEST_USER_ID, TestSession, fastapi_app


def test_other_user_cannot_access_resource_routes(client):
    with TestSession() as db:
        db.add(User(id="second-user", email="second@example.com"))
        db.add_all([
            Account(id="owned-account", user_id=TEST_USER_ID, name="Private", account_type="bank"),
            Transaction(id="owned-transaction", user_id=TEST_USER_ID, date=date(2026, 1, 1),
                        type="expense", category="Other", amount=Decimal("10"), description="Private transaction"),
            ReceiptAttachment(id="owned-receipt", user_id=TEST_USER_ID, transaction_id="owned-transaction",
                              content=b"%PDF-private", mime_type="application/pdf"),
            Goal(id="owned-goal", user_id=TEST_USER_ID, name="Private goal", target_amount=Decimal("100")),
            ImportJob(id="owned-job", user_id=TEST_USER_ID, file_name="private.csv", status="failed"),
            AIConversation(id="owned-conversation", user_id=TEST_USER_ID, title="Private"),
            Portfolio(id="owned-portfolio", user_id=TEST_USER_ID, name="Private", portfolio_type="stocks"),
            Holding(id="owned-holding", portfolio_id="owned-portfolio", symbol="ABC", name="Private holding",
                    quantity=Decimal("1"), buy_price=Decimal("10"), asset_type="equity"),
            Webhook(id="owned-webhook", user_id=TEST_USER_ID, url="https://example.com/hook",
                    events="transaction.created", secret="private-secret"),
            MerchantAlias(id="owned-alias", user_id=TEST_USER_ID, alias_key="private", canonical="Private merchant"),
            UserCategory(id="owned-category", user_id=TEST_USER_ID, name="Private category"),
            RecurringRule(id="owned-rule", user_id=TEST_USER_ID, description="Private", category="Other",
                          cadence="monthly", average_amount=Decimal("10"), minimum_amount=Decimal("10"),
                          maximum_amount=Decimal("10")),
            Notification(id="owned-notification", user_id=TEST_USER_ID, kind="alert", insight_id="private",
                         text="Private alert"),
        ])
        db.commit()

    fastapi_app.dependency_overrides[get_current_user] = lambda: UserContext(id="second-user")
    transaction = {"date": "2026-01-01", "type": "expense", "category": "Other", "amount": "10", "description": "Attempt"}
    probes = [
        ("GET", "/imports/jobs/owned-job", None),
        ("POST", "/imports/jobs/owned-job/retry", None),
        ("POST", "/imports/jobs/owned-job/cancel", None),
        ("GET", "/conversations/owned-conversation/messages", None),
        ("DELETE", "/conversations/owned-conversation", None),
        ("GET", "/transactions/owned-transaction/receipt", None),
        ("DELETE", "/transactions/owned-transaction/receipt", None),
        ("POST", "/transactions/owned-transaction/receipt", None),
        ("PUT", "/transactions/owned-transaction", transaction),
        ("POST", "/transactions/owned-transaction/undo", None),
        ("POST", "/transactions/owned-transaction/correct-category", {"category": "Dining"}),
        ("DELETE", "/transactions/owned-transaction", None),
        ("PUT", "/accounts/owned-account", {"name": "Attempt", "account_type": "cash"}),
        ("POST", "/accounts/owned-account/reconcile", {"observed_balance": "10"}),
        ("DELETE", "/accounts/owned-account", None),
        ("PUT", "/goals/owned-goal", {"name": "Attempt", "goal_type": "custom", "target_amount": "100", "current_amount": "0"}),
        ("DELETE", "/goals/owned-goal", None),
        ("POST", "/webhooks/owned-webhook/rotate", {"url": "https://example.com/hook", "events": "transaction.created", "secret": "new-secret-long-enough"}),
        ("DELETE", "/webhooks/owned-webhook", None),
        ("GET", "/portfolios/owned-portfolio/holdings", None),
        ("POST", "/portfolios/owned-portfolio/holdings", {"symbol": "XYZ", "name": "Attempt", "quantity": "1", "buy_price": "10", "asset_type": "equity"}),
        ("DELETE", "/portfolios/owned-portfolio", None),
        ("PUT", "/holdings/owned-holding", {"symbol": "XYZ", "name": "Attempt", "quantity": "1", "buy_price": "10", "asset_type": "equity"}),
        ("DELETE", "/holdings/owned-holding", None),
        ("DELETE", "/merchant-aliases/owned-alias", None),
        ("DELETE", "/categories/owned-category", None),
        ("PUT", "/recurring/owned-rule", {"description": "Attempt", "category": "Other", "cadence": "monthly", "average_amount": "10", "minimum_amount": "10", "maximum_amount": "10", "confidence": 1}),
        ("DELETE", "/recurring/owned-rule", None),
        ("POST", "/notifications/owned-notification/read", None),
    ]
    try:
        for method, path, body in probes:
            options = {"json": body} if body is not None else {}
            if path.endswith("/receipt") and method == "POST":
                options = {"files": {"file": ("receipt.pdf", b"%PDF-test", "application/pdf")}}
            response = client.request(method, path, headers={"Authorization": "Bearer second-user"}, **options)
            assert response.status_code in {403, 404}, (method, path, response.status_code)
        for path in ("/accounts", "/transactions", "/goals", "/portfolios", "/webhooks",
                     "/imports/jobs", "/conversations", "/notifications", "/export/full"):
            response = client.get(path, headers={"Authorization": "Bearer second-user"})
            assert response.status_code == 200, (path, response.status_code)
            assert "owned-" not in response.text, path
        with TestSession() as db:
            assert db.get(Transaction, "owned-transaction") is not None
            assert db.get(ReceiptAttachment, "owned-receipt") is not None
            assert db.get(Webhook, "owned-webhook") is not None
    finally:
        fastapi_app.dependency_overrides[get_current_user] = lambda: UserContext(id=TEST_USER_ID, email="test@ledger.local")

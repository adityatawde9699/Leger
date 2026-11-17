import asyncio
import json
from datetime import date
from decimal import Decimal

import pytest

import app.main as main
from app.main import _statement_row_fingerprint
from app.models import ImportJob, Transaction

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


@pytest.fixture()
def scheduled_imports(monkeypatch):
    """Capture jobs the endpoints schedule, so each test runs them deterministically.

    The test client runs every request on a short-lived event loop that is closed
    afterwards, which would abandon a background job part-way through.
    """
    scheduled = []

    def schedule(job_id):
        asyncio.get_running_loop()  # endpoints must schedule from inside the event loop
        scheduled.append(job_id)

    monkeypatch.setattr(main, "_schedule_import", schedule)
    return scheduled


def test_statement_fingerprint_is_stable_and_account_scoped():
    row = {"date": date(2026, 1, 2), "type": "expense", "amount": Decimal("100.00"), "description": "  Coffee  "}
    assert _statement_row_fingerprint(row, "account-a") == _statement_row_fingerprint(
        {**row, "description": "coffee"}, "account-a"
    )
    assert _statement_row_fingerprint(row, "account-a") != _statement_row_fingerprint(row, "account-b")
    assert _statement_row_fingerprint(row, "account-a") != _statement_row_fingerprint(
        {**row, "type": "refund"}, "account-a"
    )


def test_identical_statement_upload_returns_existing_job(client):
    content = b"Date,Description,Amount\n02/01/2026,Coffee,-100.00\n"
    first = client.post(
        "/imports/statement",
        files={"file": ("statement.csv", content, "text/csv")},
        headers=AUTH_HEADER,
    )
    assert first.status_code == 202

    second = client.post(
        "/imports/statement",
        files={"file": ("renamed-statement.csv", content, "text/csv")},
        headers=AUTH_HEADER,
    )
    assert second.status_code == 202
    assert second.json()["id"] == first.json()["id"]

    jobs = client.get("/imports/jobs?limit=10", headers=AUTH_HEADER)
    assert jobs.status_code == 200
    assert any(job["id"] == first.json()["id"] for job in jobs.json())


def test_pending_import_can_be_cancelled_without_losing_its_payload(client):
    db = TestSession()
    try:
        job = ImportJob(
            user_id=TEST_USER_ID,
            file_name="waiting.csv",
            file_extension="csv",
            file_content=b"Date,Description,Amount\n",
            status="pending",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.post(f"/imports/jobs/{job_id}/cancel", headers=AUTH_HEADER)
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    assert response.json()["cancel_requested"] is True

    db = TestSession()
    try:
        saved = db.get(ImportJob, job_id)
        assert saved.status == "cancelled"
        assert saved.file_content == b"Date,Description,Amount\n"
    finally:
        db.close()


def test_statement_review_can_exclude_preview_rows(client):
    content = b"Date,Description,Amount\n02/01/2026,Coffee,-100.00\n03/01/2026,Groceries,-250.00\n"
    preview = client.post(
        "/imports/statement/preview",
        files={"file": ("review.csv", content, "text/csv")},
        headers=AUTH_HEADER,
    )
    assert preview.status_code == 200
    rows = preview.json()["preview"]
    assert len(rows) == 2
    assert rows[0]["fingerprint"]
    assert "category_confidence" in rows[0]

    response = client.post(
        "/imports/statement",
        files={"file": ("review.csv", content, "text/csv")},
        data={"excluded_row_fingerprints": json.dumps([rows[0]["fingerprint"]])},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202
    job = response.json()
    assert rows[0]["fingerprint"] in json.loads(job["excluded_row_fingerprints"])


def test_statement_preview_review_commit_persists_only_included_rows(client, monkeypatch, scheduled_imports):
    async def categorize(rows, user_overrides=None, allow_cloud_ai=False):
        return [
            {"id": row["id"], "category": "Food", "confidence": 0.9}
            for row in rows
        ]

    monkeypatch.setattr(main, "SessionLocal", TestSession)
    monkeypatch.setattr(main, "categorize_batch", categorize)
    content = b"Date,Description,Amount\n02/01/2026,Coffee,-100.00\n03/01/2026,Groceries,-250.00\n"

    preview = client.post(
        "/imports/statement/preview",
        files={"file": ("march.csv", content, "text/csv")},
        headers=AUTH_HEADER,
    )
    assert preview.status_code == 200
    rows = preview.json()["preview"]
    assert len(rows) == 2
    assert all(row["category_confidence"] == 0.9 for row in rows)

    response = client.post(
        "/imports/statement",
        files={"file": ("march.csv", content, "text/csv")},
        data={"excluded_row_fingerprints": json.dumps([rows[0]["fingerprint"]])},
        headers=AUTH_HEADER,
    )
    assert response.status_code == 202
    job_id = response.json()["id"]

    assert scheduled_imports == [job_id]
    asyncio.run(main._process_import_job(job_id))

    db = TestSession()
    try:
        saved_job = db.get(ImportJob, job_id)
        saved_transactions = db.query(Transaction).filter(Transaction.user_id == TEST_USER_ID).all()

        assert saved_job.status == "done"
        assert saved_job.row_count == 1
        assert saved_job.processed_rows == 2
        assert [(tx.description, tx.amount, tx.category) for tx in saved_transactions] == [
            ("Groceries", Decimal("250.00"), "Food")
        ]
    finally:
        db.close()


def test_retry_failed_import_requeues_and_processes(client, monkeypatch, scheduled_imports):
    """Retry used to raise RuntimeError (no event loop in a sync route) and return 500."""
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    db = TestSession()
    try:
        job = ImportJob(
            user_id=TEST_USER_ID, status="failed", file_name="retry.csv", file_extension="csv",
            file_content=b"Date,Description,Amount\n02/01/2026,Retry coffee,-100.00\n",
            error_message="Temporary failure",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    response = client.post(f"/imports/jobs/{job_id}/retry", headers=AUTH_HEADER)

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    db = TestSession()
    try:
        assert scheduled_imports == [job_id]
        asyncio.run(main._process_import_job(job_id))
        job = db.get(ImportJob, job_id)
        assert job.status == "done"
        assert db.query(Transaction).filter(Transaction.description == "Retry coffee").count() == 1
    finally:
        db.close()


def _row(day, tx_type, amount, **extra):
    return {"date": date(2026, 3, day), "type": tx_type, "amount": Decimal(amount), "status": "posted",
            "source": "statement", **extra}


def test_imported_running_balance_accumulates_across_rows():
    rows = [_row(1, "income", "1000.00"), _row(2, "expense", "200.00"), _row(3, "expense", "50.00")]

    balances = main._imported_running_balances(rows, Decimal("500.00"))

    assert balances == [Decimal("1500.00"), Decimal("1300.00"), Decimal("1250.00")]


def test_imported_running_balance_handles_newest_first_statements():
    rows = [_row(3, "expense", "50.00"), _row(2, "expense", "200.00"), _row(1, "income", "1000.00")]

    balances = main._imported_running_balances(rows, Decimal("500.00"))

    assert balances == [Decimal("1250.00"), Decimal("1300.00"), Decimal("1500.00")]


def test_imported_running_balance_reanchors_on_bank_balance_and_skips_pending():
    rows = [
        _row(1, "expense", "100.00"),
        _row(2, "expense", "10.00", running_balance=Decimal("2000.00")),
        _row(3, "expense", "40.00", status="pending"),
        _row(4, "transfer", "30.00"),
        _row(5, "expense", "25.00"),
    ]

    balances = main._imported_running_balances(rows, Decimal("500.00"))

    assert balances == [Decimal("400.00"), Decimal("2000.00"), None, None, Decimal("1975.00")]


def test_imported_running_balance_without_prior_balance_waits_for_anchor():
    rows = [_row(1, "expense", "100.00"), _row(2, "expense", "10.00", running_balance=Decimal("900.00")),
            _row(3, "income", "50.00")]

    assert main._imported_running_balances(rows, None) == [None, Decimal("900.00"), Decimal("950.00")]


def test_statement_import_worker_carries_running_balance_between_rows(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", TestSession)
    db = TestSession()
    try:
        db.add(Transaction(
            user_id=TEST_USER_ID, date=date(2026, 1, 1), type="income", amount=Decimal("500.00"),
            category="Salary", description="Opening", source="statement", source_ref="opening",
            running_balance=Decimal("500.00"),
        ))
        job = ImportJob(
            user_id=TEST_USER_ID, status="pending", file_name="feb.csv", file_extension="csv",
            file_content=b"Date,Description,Amount\n02/02/2026,Groceries run,-100.00\n03/02/2026,Pharmacy visit,-40.00\n",
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    asyncio.run(main._process_import_job(job_id))

    db = TestSession()
    try:
        assert db.get(ImportJob, job_id).status == "done"
        balances = {
            tx.description: tx.running_balance
            for tx in db.query(Transaction).filter(Transaction.description.in_(["Groceries run", "Pharmacy visit"]))
        }
        assert balances == {"Groceries run": Decimal("400.00"), "Pharmacy visit": Decimal("360.00")}
    finally:
        db.close()


def test_import_worker_hides_internal_error_details(monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", TestSession)

    def explode(*args, **kwargs):
        raise RuntimeError("psycopg.OperationalError: connection to server at 10.1.2.3 failed")

    monkeypatch.setattr(main, "parse_csv", explode)
    db = TestSession()
    try:
        job = ImportJob(user_id=TEST_USER_ID, status="pending", file_name="x.csv", file_extension="csv",
                        file_content=b"Date,Description,Amount\n")
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    asyncio.run(main._process_import_job(job_id))

    db = TestSession()
    try:
        job = db.get(ImportJob, job_id)
        assert job.status == "failed"
        assert "10.1.2.3" not in job.error_message
        assert "server error" in job.error_message
    finally:
        db.close()


def test_stale_failed_import_payloads_are_purged_after_retention():
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    db = TestSession()
    try:
        jobs = {
            "old-failed": ImportJob(user_id=TEST_USER_ID, status="failed", updated_at=now - timedelta(days=5)),
            "old-cancelled": ImportJob(user_id=TEST_USER_ID, status="cancelled", updated_at=now - timedelta(days=5)),
            "recent-failed": ImportJob(user_id=TEST_USER_ID, status="failed", updated_at=now - timedelta(hours=1)),
            "old-pending": ImportJob(user_id=TEST_USER_ID, status="pending", updated_at=now - timedelta(days=5)),
        }
        for name, job in jobs.items():
            job.id, job.file_name, job.file_extension, job.file_content = name, f"{name}.csv", "csv", b"Date,Amount\n"
            db.add(job)
        db.commit()

        assert main._purge_stale_import_payloads(db, now=now) == 2

        remaining = {job.id: job.file_content is not None for job in db.query(ImportJob).all()}
        assert remaining == {"old-failed": False, "old-cancelled": False, "recent-failed": True, "old-pending": True}
    finally:
        db.close()

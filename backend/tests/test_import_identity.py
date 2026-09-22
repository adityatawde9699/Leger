import json
from datetime import date
from decimal import Decimal

from app.main import _statement_row_fingerprint
from app.models import ImportJob

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


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

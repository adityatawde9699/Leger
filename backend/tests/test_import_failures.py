"""Failed imports: what the user is told, whether Retry can work, and dismissing them."""
import asyncio

import pytest

import app.workers.imports as worker
from app.models import AuditLog, ImportJob, Transaction, User
from app.services.statements import StatementError

from .conftest import AUTH_HEADER, TEST_USER_ID, TestSession


def _job(**fields):
    db = TestSession()
    try:
        job = ImportJob(user_id=TEST_USER_ID, file_name="statement.csv", file_extension="csv", **fields)
        db.add(job)
        db.commit()
        return job.id
    finally:
        db.close()


def _run_failing_import(monkeypatch, error):
    monkeypatch.setattr(worker, "SessionLocal", TestSession)

    def parse(*args, **kwargs):
        raise error

    monkeypatch.setattr(worker, "parse_csv", parse)
    job_id = _job(status="pending", file_content=b"Date,Description,Amount\n")
    asyncio.run(worker._process_import_job(job_id))
    db = TestSession()
    try:
        job = db.get(ImportJob, job_id)
        return job.status, job.error_message
    finally:
        db.close()


def test_internal_parse_errors_are_not_shown_to_the_user(monkeypatch):
    # The dev database had this exact message on a failed .ods import.
    status, message = _run_failing_import(monkeypatch, ValueError("too many values to unpack (expected 2, got 4)"))

    assert status == "failed"
    assert message == worker.UNREADABLE_STATEMENT
    assert "unpack" not in message


@pytest.mark.parametrize("error", [KeyError("Date"), IndexError("list index out of range"), TypeError("bad operand")])
def test_other_parser_crashes_get_the_same_plain_message(monkeypatch, error):
    assert _run_failing_import(monkeypatch, error) == ("failed", worker.UNREADABLE_STATEMENT)


def test_statement_errors_written_for_users_are_shown(monkeypatch):
    status, message = _run_failing_import(monkeypatch, StatementError("The file has no Date column."))

    assert (status, message) == ("failed", "The file has no Date column.")


def test_job_list_says_whether_retry_can_work(client):
    retryable = _job(status="failed", file_content=b"Date,Amount\n", error_message="x")
    expired = _job(status="failed", file_content=None, error_message="x")
    done = _job(status="done", file_content=None)

    jobs = {job["id"]: job["can_retry"] for job in client.get("/imports/jobs?limit=10", headers=AUTH_HEADER).json()}

    assert jobs[retryable] is True
    assert jobs[expired] is False
    assert jobs[done] is False


def test_a_failed_import_with_an_expired_file_can_be_dismissed(client):
    job_id = _job(status="failed", file_content=None, error_message="This import failed. Upload the statement again.")
    db = TestSession()
    try:
        before = db.query(Transaction).count()
    finally:
        db.close()

    assert client.post(f"/imports/jobs/{job_id}/retry", headers=AUTH_HEADER).status_code == 410
    response = client.delete(f"/imports/jobs/{job_id}", headers=AUTH_HEADER)

    assert response.status_code == 204
    db = TestSession()
    try:
        assert db.get(ImportJob, job_id) is None
        assert db.query(Transaction).count() == before
        entry = db.query(AuditLog).filter(AuditLog.resource_id == job_id).one()
        assert (entry.action, entry.resource_type) == ("delete", "import")
    finally:
        db.close()


@pytest.mark.parametrize("status", ["pending", "processing", "done"])
def test_only_failed_or_cancelled_imports_can_be_dismissed(client, status):
    job_id = _job(status=status)

    assert client.delete(f"/imports/jobs/{job_id}", headers=AUTH_HEADER).status_code == 409


def test_another_users_import_cannot_be_dismissed(client):
    db = TestSession()
    try:
        if not db.get(User, "someone-else"):
            db.add(User(id="someone-else"))
            db.flush()
        job = ImportJob(user_id="someone-else", file_name="theirs.csv", status="failed")
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    assert client.delete(f"/imports/jobs/{job_id}", headers=AUTH_HEADER).status_code == 404

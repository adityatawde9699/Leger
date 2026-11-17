"""Blocking I/O and CPU-heavy work must run in worker threads, not on the event loop.

With a single uvicorn worker, anything blocking on the loop stalls every request.
Each fake records whether an event loop was running in the thread that called it:
asyncio.get_running_loop() succeeds only on the loop's own thread.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

import app.rate_limit as rate_limit
import app.workers.imports as worker
import app.workers.maintenance as maintenance
from app.config import settings
from app.models import AppSession, ImportJob
from app.services import statements
from app.services.ai_budget import AIRequestBudget
from app.services.ai_router import AIRouter

from .conftest import TEST_USER_ID, TestSession
from .test_ai_router import FakeAdapter


def _on_event_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_rate_limit_store_is_called_off_the_event_loop(client, monkeypatch):
    calls = []

    class Pipeline:
        def incr(self, key):
            pass

        def expire(self, key, seconds):
            pass

        def exec(self):
            calls.append(_on_event_loop())
            return [1, True]

    class Store:
        def pipeline(self):
            return Pipeline()

    monkeypatch.setattr(rate_limit, "security_rate_store", Store())

    client.post("/categorize", json={"description": "Coffee"}, headers={"Authorization": "Bearer x"})

    assert calls == [False]


def test_statement_parsing_and_row_saving_run_off_the_event_loop(monkeypatch):
    monkeypatch.setattr(worker, "SessionLocal", TestSession)
    seen = {}

    def fake_parse_csv(content):
        seen["parse"] = _on_event_loop()
        return [{"date": "2026-03-01", "type": "expense", "category": "Food", "amount": "12.00",
                 "description": "Threaded lunch", "source": "statement"}]

    real_save = worker._save_imported_rows

    def spy_save(*args):
        seen["save"] = _on_event_loop()
        return real_save(*args)

    monkeypatch.setattr(worker, "parse_csv", fake_parse_csv)
    monkeypatch.setattr(worker, "_save_imported_rows", spy_save)
    with TestSession() as db:
        job = ImportJob(user_id=TEST_USER_ID, status="pending", file_name="a.csv", file_extension="csv",
                        file_content=b"x")
        db.add(job)
        db.commit()
        job_id = job.id

    asyncio.run(worker._process_import_job(job_id))

    assert seen == {"parse": False, "save": False}
    with TestSession() as db:
        assert db.get(ImportJob, job_id).status == "done"


def test_pdf_extraction_runs_off_the_event_loop(monkeypatch):
    seen = []
    monkeypatch.setattr(statements, "_parse_pdf_locally", lambda content: seen.append(_on_event_loop()) or [])

    assert asyncio.run(statements.parse_pdf(b"%PDF-1.4", allow_cloud_ai=False)) == []
    assert seen == [False]


def test_shared_ai_budget_check_runs_off_the_event_loop(monkeypatch):
    seen = []

    class Redis:
        def incr(self, key):
            seen.append(_on_event_loop())
            return 1

        def expire(self, key, seconds):
            pass

    router = AIRouter()
    router.adapters = [("Only", FakeAdapter(result="ok"))]
    router._budget = AIRequestBudget(redis_client=Redis(), global_limit=10)
    monkeypatch.setattr(settings, "ai_provider_allowlist", "")
    monkeypatch.setattr(settings, "ai_task_provider_policy", "")

    assert asyncio.run(router.generate("system", task_type="advisor")) == "ok"
    assert seen == [False]


@pytest.mark.parametrize("uses_redis", [False, True])
def test_budget_reports_when_it_needs_the_network(uses_redis):
    budget = AIRequestBudget(redis_client=object() if uses_redis else None, global_limit=5)
    assert budget.uses_network("any") is uses_redis
    assert AIRequestBudget(redis_client=object(), global_limit=0).uses_network("any") is False


def test_maintenance_cycle_is_synchronous_and_purges_expired_sessions(monkeypatch):
    monkeypatch.setattr(maintenance, "SessionLocal", TestSession)
    now = datetime.now(UTC)
    with TestSession() as db:
        db.add(AppSession(token_hash="expired", user_id=TEST_USER_ID, created_at=now - timedelta(days=2),
                          reauthed_at=now - timedelta(days=2), expires_at=now - timedelta(days=1)))
        db.commit()

    maintenance._run_maintenance_cycle()  # plain function: the loop runs it with asyncio.to_thread

    with TestSession() as db:
        assert db.get(AppSession, "expired") is None

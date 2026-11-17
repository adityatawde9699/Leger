"""Alembic migrations must produce exactly the schema the models declare."""

from datetime import date, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.db import Base
from app.migrate import upgrade_schema

from .conftest import TEST_ENGINE


@pytest.fixture()
def engine():
    """A database with nothing in it, separate from the per-test schema in conftest."""
    if TEST_ENGINE.dialect.name == "sqlite":
        eng = create_engine("sqlite://")
        yield eng
        eng.dispose()
        return
    # PostgreSQL: conftest creates the model tables before each test; start empty instead.
    Base.metadata.drop_all(bind=TEST_ENGINE)
    with TEST_ENGINE.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    yield TEST_ENGINE
    with TEST_ENGINE.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))


def _schema_diff(conn) -> list:
    return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


def test_migrations_build_the_model_schema_from_empty(engine):
    with engine.begin() as conn:
        upgrade_schema(conn)
    with engine.connect() as conn:
        assert _schema_diff(conn) == []


def test_migrations_are_idempotent(engine):
    with engine.begin() as conn:
        upgrade_schema(conn)
    with engine.begin() as conn:
        upgrade_schema(conn)
        assert conn.execute(text("SELECT count(*) FROM alembic_version")).scalar() == 1


def test_baseline_upgrades_a_legacy_database_in_place(engine):
    """Older deployments have tables from create_all but lack later columns."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id VARCHAR(64) PRIMARY KEY, email VARCHAR(255), "
                          "created_at TIMESTAMP)"))
        conn.execute(text("INSERT INTO users (id, email) VALUES ('legacy-user', 'old@example.com')"))
    with engine.begin() as conn:
        upgrade_schema(conn)
    with engine.connect() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("users")}
        assert {"cloud_ai_enabled", "quiet_hours_start", "proactive_daily_cap"} <= columns
        row = conn.execute(text("SELECT cloud_ai_enabled, currency_preference FROM users")).one()
        # Cloud AI stays opt-in for users who never chose it.
        assert not row.cloud_ai_enabled
        assert row.currency_preference == "INR"


def test_duplicate_source_refs_are_retagged_not_deleted(engine):
    from alembic import command

    from app.migrate import alembic_config

    with engine.begin() as conn:
        command.upgrade(alembic_config(conn), "0001")
        conn.execute(text("INSERT INTO users (id, currency_preference, region, pay_cycle, risk_comfort, "
                          "household_mode, recurring_tolerance, onboarding_completed, cloud_ai_enabled, "
                          "insight_frequency, quiet_hours_start, quiet_hours_end, proactive_daily_cap, created_at) "
                          "VALUES ('u1', 'INR', 'IN', 'monthly', 'not_sure', 'individual', 'standard', false, false, "
                          "'daily', 22, 7, 3, CURRENT_TIMESTAMP)"))
        for tx_id, ref, minute in (("a", "fp1", 1), ("b", "fp1", 2), ("c", "split:g", 3), ("d", "split:g", 4)):
            conn.execute(text(
                "INSERT INTO transactions (id, user_id, date, type, status, category, amount, description, "
                "source, source_ref, created_at) VALUES (:id, 'u1', :day, 'expense', 'posted', 'Food', "
                "10, 'x', 'statement', :ref, :created)"
            ), {"id": tx_id, "ref": ref, "day": date(2026, 3, 1), "created": datetime(2026, 3, 1, 10, minute)})
    with engine.begin() as conn:
        upgrade_schema(conn)
    with engine.connect() as conn:
        refs = dict(conn.execute(text("SELECT id, source_ref FROM transactions ORDER BY id")).all())
    assert refs == {"a": "fp1", "b": "dup:b", "c": "split:g", "d": "split:g"}

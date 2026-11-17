"""Alembic migrations must produce exactly the schema the models declare."""

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


import pytest

from app.config import Settings


@pytest.mark.parametrize(("given", "expected"), [
    ("postgresql://u:p@db.neon.tech/ledger?sslmode=require", "postgresql+psycopg://u:p@db.neon.tech/ledger?sslmode=require"),
    ("postgres://u:p@host:5432/ledger", "postgresql+psycopg://u:p@host:5432/ledger"),
    ("postgresql+psycopg://u:p@host/ledger", "postgresql+psycopg://u:p@host/ledger"),
    ("sqlite:///./ledger_dev.db", "sqlite:///./ledger_dev.db"),
])
def test_database_url_uses_the_installed_psycopg3_driver(given, expected):
    assert Settings(_env_file=None, database_url=given).database_url == expected


def test_plain_postgres_url_builds_an_engine_without_psycopg2():
    from sqlalchemy import create_engine

    url = Settings(_env_file=None, database_url="postgresql://u:p@localhost/ledger").database_url
    engine = create_engine(url, connect_args={"prepare_threshold": None})
    assert engine.dialect.driver == "psycopg"

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

if _is_sqlite:
    # SQLite: use default pool + thread guard
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
else:
    # Neon / PostgreSQL via PgBouncer (transaction mode):
    # 1. NullPool — disable SQLAlchemy's internal pooler; let Neon's PgBouncer handle pooling.
    # 2. pool_pre_ping — detect stale/paused connections before use (critical for serverless).
    # 3. prepare_threshold=None — disable psycopg3 protocol-level prepared statements;
    #    PgBouncer transaction mode does not support them and will raise errors.
    engine = create_engine(
        settings.database_url,
        poolclass=NullPool,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

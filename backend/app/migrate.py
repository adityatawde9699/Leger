"""Bring the database schema up to date. Run as `python -m app.migrate`.

Production runs this from entrypoint.sh before the server starts; development
runs it on app startup unless RUN_DB_BOOTSTRAP=false.
"""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection

BACKEND_DIR = Path(__file__).resolve().parent.parent

logger = logging.getLogger("ledger.migrate")


def alembic_config(connection: Connection | None = None) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["configure_logger"] = False
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_schema(connection: Connection | None = None) -> None:
    """Apply every pending Alembic revision."""
    command.upgrade(alembic_config(connection), "head")


def run_migrations() -> None:
    """Schema migrations, then data migrations that need application code."""
    from .db import SessionLocal
    from .services.webhook_secrets import migrate_plaintext_secrets

    upgrade_schema()
    with SessionLocal() as db:
        migrated = migrate_plaintext_secrets(db)
    logger.info("migrations.complete legacy_webhook_secrets_encrypted=%d", migrated)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    run_migrations()

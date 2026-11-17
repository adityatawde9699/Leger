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
    """Apply schema migrations; the entry point for entrypoint.sh and dev startup."""
    upgrade_schema()
    logger.info("migrations.complete")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    run_migrations()

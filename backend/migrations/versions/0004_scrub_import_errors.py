"""Replace raw exception text stored on failed import jobs.

Before this release the import worker stored str(exc) for any ValueError, so some
failed jobs show internal Python errors (for example "too many values to unpack")
to the user. Messages the app writes itself are kept; anything else becomes a
neutral instruction. Data only: there is no schema change.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

# Copied rather than imported: a migration must keep working after the app changes.
APP_MESSAGES = (
    "Ledger couldn't read this statement. Check that it is an unedited export from your bank "
    "(CSV, XLS, XLSX, ODS or PDF) and upload it again.",
    "Import failed because of a server error. Please retry the import.",
    "Import payload is unavailable; please upload the statement again.",
    "No transactions could be extracted from this file. If this is a scanned/image PDF, "
    "export a digital PDF or CSV from your bank and re-upload.",
)
ROW_LIMIT_PATTERN = "Statement has % rows, over the %-row limit.%"
LEGACY_FAILURE = "This import failed. Upload the statement again."


def upgrade() -> None:
    jobs = sa.table("import_jobs", sa.column("status", sa.String), sa.column("error_message", sa.Text))
    op.execute(
        jobs.update()
        .where(
            jobs.c.status == "failed",
            jobs.c.error_message.isnot(None),
            jobs.c.error_message.notin_(APP_MESSAGES),
            ~jobs.c.error_message.like(ROW_LIMIT_PATTERN),
        )
        .values(error_message=LEGACY_FAILURE)
    )


def downgrade() -> None:
    # The original exception text is intentionally not kept.
    pass

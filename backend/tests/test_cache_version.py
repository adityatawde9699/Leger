from datetime import UTC, datetime, timedelta

from app.main import _user_cache_version
from app.models import AuditLog

from .conftest import TEST_USER_ID, TestSession


def test_user_cache_version_changes_when_audited_data_changes():
    db = TestSession()
    try:
        first = _user_cache_version(db, TEST_USER_ID)
        db.add(AuditLog(
            user_id=TEST_USER_ID,
            action="update",
            resource_type="transaction",
            resource_id="tx-1",
            created_at=datetime.now(UTC) - timedelta(seconds=1),
        ))
        db.commit()
        second = _user_cache_version(db, TEST_USER_ID)
    finally:
        db.close()

    assert first != second
    assert second.startswith("1:")

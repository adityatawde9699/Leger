"""
Shared test fixtures — in-memory SQLite database and FastAPI test client.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.db import Base, get_db
from app.main import app
from app.models import User
from app.schemas import UserContext

# In-memory SQLite for tests
TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(bind=TEST_ENGINE)

# Stable test identity
TEST_USER_ID = "test-user-1"
TEST_USER = UserContext(id=TEST_USER_ID, email="test@ledger.local")
AUTH_HEADER = {"Authorization": f"Bearer {TEST_USER_ID}"}


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user() -> UserContext:
    """Bypass JWT verification — return a stable test user."""
    return TEST_USER


# Register dependency overrides (unwrap CORSMiddleware to access the FastAPI app instance)
fastapi_app = getattr(app, "app", app)
fastapi_app.dependency_overrides[get_db] = override_get_db
fastapi_app.dependency_overrides[get_current_user] = override_get_current_user


@pytest.fixture(autouse=True)
def setup_db():
    """Create all tables before each test, drop after. Pre-seed the test user."""
    Base.metadata.create_all(bind=TEST_ENGINE)
    # Pre-create the user row so FK constraints in every endpoint are satisfied
    db = TestSession()
    try:
        if not db.get(User, TEST_USER_ID):
            db.add(User(id=TEST_USER_ID, email="test@ledger.local"))
            db.commit()
    finally:
        db.close()
    yield
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture()
def client():
    """FastAPI test client."""
    return TestClient(app)

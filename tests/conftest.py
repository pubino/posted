import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
import os

# Set testing environment variables before importing code modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["DEV_MODE"] = "True"
os.environ["DRUPAL_WEBHOOK_TOKEN"] = "test_webhook_token"
os.environ["NAMETAGS_WEBHOOK_TOKEN"] = "test_webhook_token"
os.environ["ALLOWED_ADMIN_PRINCIPALS"] = "bino@princeton.edu"
os.environ["TARGET_HOST"] = "https://caarms.princeton.edu"

from backend.main import app, get_db
from backend.database import Base

# Setup shared in-memory SQLite database
engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="function")
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

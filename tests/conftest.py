import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock
import sys
import os

from app.main import app
from app.core.database import get_db
from app.models import GlobalApiKey, Base, Task
from app.middleware.auth import get_api_key

# Setup in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test."""
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def client(db_session):
    """Create a test client with overridden dependencies."""
    
    # Override get_db
    def override_get_db():
        try:
            yield db_session
        finally:
            pass
            
    # Create a mock API key in the DB
    mock_key = GlobalApiKey(
        name="Test Key",
        hashed_key="mock_hash",
        prefix="mock_prefix",
        is_active=True
    )
    db_session.add(mock_key)
    db_session.commit()
    db_session.refresh(mock_key)
    
    # Override get_api_key
    def override_get_api_key():
        return mock_key
        
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_api_key] = override_get_api_key
    
    with TestClient(app) as c:
        yield c
        
    app.dependency_overrides = {}

@pytest.fixture
def mock_s3(monkeypatch):
    """Mock S3 service functions."""
    mock_get_object = MagicMock()
    # Default behavior: return an object with a body
    mock_body = MagicMock()
    mock_body.read.return_value = b"fake audio content"
    # Make body iterable for StreamingResponse
    def iter_content():
        yield b"fake audio content"
    mock_body.__iter__ = iter_content
    
    mock_get_object.return_value = {
        'Body': mock_body,
        'ContentType': 'audio/mpeg'
    }
    
    monkeypatch.setattr("app.services.s3_service.get_s3_object", mock_get_object)
    return mock_get_object

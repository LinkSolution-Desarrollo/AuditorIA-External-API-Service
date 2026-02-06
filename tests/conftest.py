import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.middleware.auth import get_api_key
from app.models import GlobalApiKey

# Mock Auth to bypass DB lookup for unit tests
async def override_get_api_key():
    return GlobalApiKey(id=1, name="Test Key", hashed_key="mock", prefix="mock", is_active=True)

@pytest.fixture
def client():
    # Allow overriding dependencies
    app.dependency_overrides[get_api_key] = override_get_api_key
    client = TestClient(app)
    yield client
    app.dependency_overrides = {}

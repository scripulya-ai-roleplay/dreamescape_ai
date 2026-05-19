import pytest
import requests


@pytest.fixture(scope="function")
def client():
    """HTTP client for e2e tests with 30-second timeout."""
    session = requests.Session()
    session.timeout = 30.0  # 30 seconds timeout as requested
    session.base_url = "http://localhost:8000"
    
    # Create a wrapper class to handle base URL
    class ClientWrapper:
        def __init__(self, session, base_url):
            self.session = session
            self.base_url = base_url
        
        def get(self, path, **kwargs):
            return self.session.get(f"{self.base_url}{path}", timeout=30.0, **kwargs)
        
        def post(self, path, **kwargs):
            return self.session.post(f"{self.base_url}{path}", timeout=30.0, **kwargs)
        
        def delete(self, path, **kwargs):
            return self.session.delete(f"{self.base_url}{path}", timeout=30.0, **kwargs)
    
    return ClientWrapper(session, "http://localhost:8000")


@pytest.fixture
def auth_headers():
    """Mock authentication headers for testing."""
    # For now, return empty headers since we don't have a clear auth endpoint
    # This can be updated when auth is properly implemented
    return {}
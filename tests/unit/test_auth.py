import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend.server.app import create_app
from backend.server.service import ERISEngineService

@pytest.fixture
def mock_service():
    service = MagicMock(spec=ERISEngineService)
    service.provider_name = "gemini"
    service.model_name = "gemini-3.5-flash"
    service.get_providers_info.return_value = {
        "active_provider": "gemini",
        "model_name": "gemini-3.5-flash",
        "supported_providers": ["gemini", "openrouter", "ollama"]
    }
    return service

def test_auth_disabled_allows_requests(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")
    monkeypatch.delenv("ERIS_API_KEY", raising=False)
    
    app = create_app(service=mock_service)
    client = TestClient(app)
    
    response = client.get("/api/providers")
    assert response.status_code == 200
    assert response.json()["active_provider"] == "gemini"

def test_auth_enabled_rejects_missing_key(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("ERIS_API_KEY", "secret_key_123")
    
    app = create_app(service=mock_service)
    client = TestClient(app)
    
    response = client.get("/api/providers")
    assert response.status_code == 401
    assert "Unauthorized" in response.json()["detail"]

def test_auth_enabled_rejects_invalid_key(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("ERIS_API_KEY", "secret_key_123")
    
    app = create_app(service=mock_service)
    client = TestClient(app)
    
    response = client.get("/api/providers", headers={"X-ERIS-API-Key": "wrong_key"})
    assert response.status_code == 401

def test_auth_enabled_accepts_valid_header_key(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("ERIS_API_KEY", "secret_key_123")
    
    app = create_app(service=mock_service)
    client = TestClient(app)
    
    response = client.get("/api/providers", headers={"X-ERIS-API-Key": "secret_key_123"})
    assert response.status_code == 200
    assert response.json()["active_provider"] == "gemini"

def test_auth_enabled_accepts_valid_bearer_token(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("ERIS_API_KEY", "secret_key_123")
    
    app = create_app(service=mock_service)
    client = TestClient(app)
    
    response = client.get("/api/providers", headers={"Authorization": "Bearer secret_key_123"})
    assert response.status_code == 200
    assert response.json()["active_provider"] == "gemini"

from backend.core.version import VERSION

def test_health_endpoint_remains_unauthenticated(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "true")
    monkeypatch.setenv("ERIS_API_KEY", "secret_key_123")
    mock_service.get_health.return_value = {
        "status": "ok",
        "version": VERSION,
        "active_provider": "gemini",
        "model": "gemini-3.5-flash",
        "auth_enabled": True
    }
    
    app = create_app(service=mock_service)
    client = TestClient(app)
    
    # Health endpoint does not require auth headers
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["auth_enabled"] is True

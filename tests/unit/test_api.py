import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from backend.server.app import create_app
from backend.server.service import ERISEngineService
from backend.core.version import VERSION

@pytest.fixture
def mock_service():
    service = MagicMock(spec=ERISEngineService)
    service.provider_name = "gemini"
    service.model_name = "gemini-3.5-flash"
    
    service.get_health.return_value = {
        "status": "ok",
        "version": VERSION,
        "active_provider": "gemini",
        "model": "gemini-3.5-flash"
    }
    service.get_providers_info.return_value = {
        "active_provider": "gemini",
        "model_name": "gemini-3.5-flash",
        "supported_providers": ["gemini", "openrouter", "ollama"]
    }
    service.get_tools_info.return_value = [
        {"name": "system_info", "description": "Returns system metrics"},
        {"name": "launch_application", "description": "Launches desktop app"}
    ]
    service.get_memory.return_value = [
        {"role": "user", "text": "Hello ERIS"},
        {"role": "assistant", "text": "Greetings"}
    ]
    service.process_chat.return_value = {
        "response": "Hello! I am ERIS.",
        "provider": "gemini",
        "model": "gemini-3.5-flash"
    }
    def mock_stream(prompt, clear_history=False):
        yield "Hello! "
        yield "I am "
        yield "ERIS."
    service.process_chat_stream.side_effect = mock_stream
    return service

@pytest.fixture
def client(monkeypatch, mock_service):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")
    monkeypatch.delenv("ERIS_API_KEY", raising=False)
    app = create_app(service=mock_service)
    return TestClient(app)

def test_api_health_endpoint(client, mock_service):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == VERSION
    assert data["active_provider"] == "gemini"
    mock_service.get_health.assert_called_once()

def test_api_providers_endpoint(client, mock_service):
    response = client.get("/api/providers")
    assert response.status_code == 200
    data = response.json()
    assert data["active_provider"] == "gemini"
    assert "openrouter" in data["supported_providers"]

def test_api_tools_endpoint(client, mock_service):
    response = client.get("/api/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["tools"][0]["name"] == "system_info"

def test_api_memory_endpoints(client, mock_service):
    # Test GET memory
    response_get = client.get("/api/memory")
    assert response_get.status_code == 200
    data_get = response_get.json()
    assert data_get["count"] == 2
    assert data_get["history"][0]["text"] == "Hello ERIS"

    # Test DELETE memory
    response_del = client.delete("/api/memory")
    assert response_del.status_code == 200
    mock_service.clear_memory.assert_called_once()

def test_api_chat_endpoint(client, mock_service):
    payload = {"prompt": "What is system status?", "clear_history": False}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Hello! I am ERIS."
    assert data["provider"] == "gemini"
    mock_service.process_chat.assert_called_once_with(prompt="What is system status?", clear_history=False)

def test_api_chat_stream_endpoint(client, mock_service):
    payload = {"prompt": "Tell me a story", "clear_history": False}
    response = client.post("/api/chat/stream", json=payload)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    content = response.text
    assert "Hello! " in content
    assert "ERIS." in content
    assert "[DONE]" in content


def test_api_chat_error_sanitization(client, mock_service):
    mock_service.process_chat.side_effect = RuntimeError("Sensitive path leaked: C:\\Secret\\Keys\\db.sqlite")
    payload = {"prompt": "Trigger crash", "clear_history": False}
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 500
    data = response.json()
    assert "An internal server error occurred." in data["detail"]
    assert "Sensitive path leaked" not in data["detail"]


def test_api_chat_stream_error_sanitization(client, mock_service):
    def crashing_stream(prompt, clear_history=False):
        raise RuntimeError("Internal crash with secret token XYZ123")
    mock_service.process_chat_stream.side_effect = crashing_stream
    payload = {"prompt": "Trigger stream crash", "clear_history": False}
    response = client.post("/api/chat/stream", json=payload)
    assert response.status_code == 200
    content = response.text
    assert "An internal error occurred processing your request." in content
    assert "XYZ123" not in content

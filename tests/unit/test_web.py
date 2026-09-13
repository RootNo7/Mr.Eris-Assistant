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
    return service

@pytest.fixture
def client(mock_service):
    app = create_app(service=mock_service)
    return TestClient(app)

def test_web_index_html_delivery(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "<title>ERIS" in response.text
    assert "apps/web" not in response.text or "ERIS" in response.text

def test_web_static_css_delivery(client):
    response = client.get("/src/css/style.css")
    assert response.status_code == 200
    assert "--bg-main" in response.text

def test_web_static_js_delivery(client):
    response = client.get("/src/js/app.js")
    assert response.status_code == 200
    assert "DOMContentLoaded" in response.text

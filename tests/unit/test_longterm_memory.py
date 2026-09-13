import os
import tempfile
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from backend.ai.memory.sqlite_memory import LongTermMemoryStore
from backend.ai.memory.extractor import MemoryExtractor
from backend.server.app import create_app
from backend.server.service import ERISEngineService

@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    store = LongTermMemoryStore(db_path=db_path)
    yield store
    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except OSError:
            pass

def test_sqlite_memory_crud(temp_db):
    # 1. Store facts
    fact1 = temp_db.store_fact(key="user_name", value="Faisal", category="user_profile")
    assert fact1["key"] == "user_name"
    assert fact1["value"] == "Faisal"

    # 2. Get fact
    retrieved = temp_db.get_fact("user_name")
    assert retrieved is not None
    assert retrieved["value"] == "Faisal"

    # 3. Update fact
    updated = temp_db.store_fact(key="user_name", value="Hafiz Faisal", category="user_profile")
    assert updated["value"] == "Hafiz Faisal"

    # 4. List facts
    all_facts = temp_db.get_all_facts()
    assert len(all_facts) == 1

    # 5. Delete fact
    deleted = temp_db.delete_fact("user_name")
    assert deleted is True
    assert temp_db.get_fact("user_name") is None

def test_sqlite_memory_search_and_formatting(temp_db):
    temp_db.store_fact(key="preferred_editor", value="VS Code", category="preference")
    temp_db.store_fact(key="favorite_language", value="Python", category="preference")
    
    # Search
    results = temp_db.search_facts("editor")
    assert len(results) >= 1
    assert results[0]["key"] == "preferred_editor"

    # Format context
    formatted = temp_db.format_recalled_facts_context("What editor do I use?")
    assert "[RECALLED LONG-TERM MEMORY FACTS]" in formatted
    assert "Preferred Editor: VS Code" in formatted

def test_memory_extractor(temp_db):
    extractor = MemoryExtractor(memory_store=temp_db)
    
    # Test "My name is Faisal"
    extracted1 = extractor.extract_and_store("Hello, my name is Faisal!")
    assert len(extracted1) == 1
    assert temp_db.get_fact("user_name")["value"] == "Faisal"

    # Test "Remember that my favorite editor is VS Code"
    extracted2 = extractor.extract_and_store("Please remember that favorite editor is VS Code")
    assert len(extracted2) == 1
    assert temp_db.get_fact("favorite_editor")["value"] == "VS Code"

@pytest.fixture
def mock_service_with_memory(temp_db):
    service = MagicMock(spec=ERISEngineService)
    service.provider_name = "gemini"
    service.model_name = "gemini-3.5-flash"
    
    service.get_facts.side_effect = lambda: temp_db.get_all_facts()
    service.add_fact.side_effect = lambda key, value, category="general": temp_db.store_fact(key, value, category)
    service.delete_fact.side_effect = lambda key: temp_db.delete_fact(key)
    return service

def test_facts_api_endpoints(monkeypatch, mock_service_with_memory, temp_db):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")
    monkeypatch.delenv("ERIS_API_KEY", raising=False)

    app = create_app(service=mock_service_with_memory)
    client = TestClient(app)

    # 1. GET /api/memory/facts (Empty)
    res_get = client.get("/api/memory/facts")
    assert res_get.status_code == 200
    assert res_get.json()["count"] == 0

    # 2. POST /api/memory/facts
    res_post = client.post("/api/memory/facts", json={"key": "project_name", "value": "ERIS AI", "category": "project"})
    assert res_post.status_code == 200
    assert res_post.json()["key"] == "project_name"

    # 3. GET /api/memory/facts (1 item)
    res_get2 = client.get("/api/memory/facts")
    assert res_get2.status_code == 200
    assert res_get2.json()["count"] == 1

    # 4. DELETE /api/memory/facts/project_name
    res_del = client.delete("/api/memory/facts/project_name")
    assert res_del.status_code == 200
    assert "deleted successfully" in res_del.json()["message"]

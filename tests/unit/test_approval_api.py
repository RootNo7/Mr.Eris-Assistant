import pytest
from fastapi.testclient import TestClient
from backend.server.app import create_app
from backend.server.service import ERISEngineService
from backend.security.enums import RiskLevel, ApprovalState


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Disable auth so tests are not coupled to live API-key configuration.
    # This is the established pattern across all other ERIS API tests.
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")

    service = ERISEngineService()
    # Use temporary store to isolate tests
    db_file = tmp_path / "test_api_approvals.db"
    from backend.storage.approval_store import ApprovalStore
    from backend.security.approval import ApprovalManager
    store = ApprovalStore(db_path=str(db_file))
    service.approval_manager = ApprovalManager(store=store)
    service.tool_registry.executor.approval_manager = service.approval_manager

    app = create_app(service=service)
    with TestClient(app) as test_client:
        yield test_client, service


def test_api_approvals_workflow(client):
    test_client, service = client

    # Initially pending list is empty
    res = test_client.get("/api/approvals/pending")
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 0

    # Create a pending approval request via service
    req = service.approval_manager.create_request(
        tool_name="RunPCCommandTool",
        risk_level=RiskLevel.T3,
        args={"command": "dir"},
        scope="system"
    )

    # Now pending list returns 1 item
    res_list = test_client.get("/api/approvals/pending")
    assert res_list.status_code == 200
    assert res_list.json()["count"] == 1
    assert res_list.json()["approvals"][0]["approval_id"] == req.approval_id

    # Get specific approval details
    res_detail = test_client.get(f"/api/approvals/{req.approval_id}")
    assert res_detail.status_code == 200
    assert res_detail.json()["tool_name"] == "RunPCCommandTool"

    # Approve request via API
    res_approve = test_client.post(
        f"/api/approvals/{req.approval_id}/approve",
        json={"decided_by": "api_user"},
    )
    assert res_approve.status_code == 200
    assert res_approve.json()["approval"]["state"] == "approved"
    assert res_approve.json()["approval"]["decided_by"] == "api_user"


def test_api_approval_not_found(client):
    test_client, service = client

    res = test_client.get("/api/approvals/invalid_id_12345")
    assert res.status_code == 404

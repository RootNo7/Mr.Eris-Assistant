import time
import pytest
from backend.security.enums import RiskLevel, ApprovalState, ApprovalDecisionAction
from backend.security.approval_models import (
    ApprovalRequest,
    redact_sensitive_arguments,
    compute_raw_args_hash,
    compute_binding_hash
)
from backend.security.approval import ApprovalManager
from backend.storage.approval_store import ApprovalStore


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_approvals.db"
    store = ApprovalStore(db_path=str(db_file))
    yield store
    store.clear()


@pytest.fixture
def manager(temp_store):
    return ApprovalManager(store=temp_store, default_ttl_seconds=10.0)


def test_redact_sensitive_arguments():
    raw_args = {
        "command": "dir",
        "password": "SuperSecretPassword123!",
        "api_key": "sk-1234567890abcdef",
        "nested": {
            "bearer_token": "token123",
            "normal_param": "hello"
        }
    }
    redacted = redact_sensitive_arguments(raw_args)
    assert redacted["command"] == "dir"
    assert redacted["password"] == "<redacted>"
    assert redacted["api_key"] == "<redacted>"
    assert redacted["nested"]["bearer_token"] == "<redacted>"
    assert redacted["nested"]["normal_param"] == "hello"


def test_compute_binding_hash():
    args = {"command": "echo test"}
    raw_hash = compute_raw_args_hash(args)
    binding = compute_binding_hash("user", "RunPCCommandTool", "execute", "system", "tool.execute", raw_hash)
    assert isinstance(binding, str)
    assert len(binding) == 64

    # Changing any component changes the binding hash
    binding_mutated = compute_binding_hash("user", "RunPCCommandTool", "execute", "forbidden_scope", "tool.execute", raw_hash)
    assert binding != binding_mutated


def test_create_and_get_request(manager):
    req = manager.create_request(
        tool_name="RunPCCommandTool",
        risk_level=RiskLevel.T3,
        args={"command": "ipconfig", "secret_key": "mysecret"},
        scope="system"
    )
    assert req.approval_id is not None
    assert req.state == ApprovalState.PENDING
    assert req.arguments["secret_key"] == "<redacted>"
    assert req.arguments["command"] == "ipconfig"

    fetched = manager.get_request(req.approval_id)
    assert fetched is not None
    assert fetched.approval_id == req.approval_id
    assert fetched.state == ApprovalState.PENDING


def test_approval_lifecycle_approve(manager):
    req = manager.create_request("LaunchAppTool", RiskLevel.T2, {"app_name": "notepad"}, "pc")
    assert req.state == ApprovalState.PENDING

    approved_req = manager.approve(req.approval_id, decided_by="admin_user")
    assert approved_req.state == ApprovalState.APPROVED
    assert approved_req.decided_by == "admin_user"
    assert approved_req.decided_at is not None


def test_approval_lifecycle_reject(manager):
    req = manager.create_request("RunPCCommandTool", RiskLevel.T3, {"command": "shutdown /s"}, "system")
    rejected_req = manager.reject(req.approval_id, decided_by="user")
    assert rejected_req.state == ApprovalState.REJECTED
    assert rejected_req.decided_by == "user"


def test_approval_lifecycle_cancel(manager):
    req = manager.create_request("WriteFileTool", RiskLevel.T2, {"file_path": "test.txt", "content": "x"}, "files")
    cancelled_req = manager.cancel(req.approval_id, decided_by="user")
    assert cancelled_req.state == ApprovalState.CANCELLED


def test_invalid_state_transitions(manager):
    req = manager.create_request("RunPCCommandTool", RiskLevel.T3, {"command": "dir"}, "system")
    manager.reject(req.approval_id)

    # Attempting to approve a REJECTED request must raise ValueError
    with pytest.raises(ValueError, match="terminal state"):
        manager.approve(req.approval_id)


def test_expiration_behavior(temp_store):
    mgr = ApprovalManager(store=temp_store, default_ttl_seconds=0.1)
    req = mgr.create_request("RunPCCommandTool", RiskLevel.T3, {"command": "dir"}, "system")

    time.sleep(0.15)  # Wait past TTL

    # Accessing request updates state to EXPIRED
    fetched = mgr.get_request(req.approval_id)
    assert fetched.state == ApprovalState.EXPIRED

    # Cannot approve an expired request
    with pytest.raises(ValueError, match="expired"):
        mgr.approve(req.approval_id)


def test_deduplication(manager):
    req1 = manager.create_request("RunPCCommandTool", RiskLevel.T3, {"command": "dir"}, "system", session_id="s1")
    req2 = manager.create_request("RunPCCommandTool", RiskLevel.T3, {"command": "dir"}, "system", session_id="s1")

    # Identical pending request returns existing approval_id
    assert req1.approval_id == req2.approval_id

import time
import pytest
from backend.security.enums import RiskLevel, ApprovalState
from backend.security.approval_models import ApprovalRequest, compute_raw_args_hash, compute_binding_hash
from backend.storage.approval_store import ApprovalStore


@pytest.fixture
def store(tmp_path):
    db_file = tmp_path / "test_store.db"
    s = ApprovalStore(db_path=str(db_file))
    yield s
    s.clear()


def test_approval_store_crud(store):
    args = {"command": "dir"}
    raw_hash = compute_raw_args_hash(args)
    binding = compute_binding_hash("user", "RunPCCommandTool", "execute", "system", "tool.execute", raw_hash)

    req = ApprovalRequest(
        approval_id="app-1",
        request_id="req-1",
        principal_id="user",
        tool_name="RunPCCommandTool",
        action="execute",
        arguments=args,
        raw_arguments_hash=raw_hash,
        resource_scope="system",
        permission="tool.execute",
        risk_level=RiskLevel.T3,
        reason="Testing",
        created_at=time.time(),
        expires_at=time.time() + 100,
        state=ApprovalState.PENDING,
        binding_hash=binding
    )

    store.store_request(req)

    fetched = store.get_request("app-1")
    assert fetched is not None
    assert fetched.approval_id == "app-1"
    assert fetched.state == ApprovalState.PENDING

    # Update state
    updated = store.update_state("app-1", new_state=ApprovalState.APPROVED, decided_by="admin")
    assert updated is True

    fetched_updated = store.get_request("app-1")
    assert fetched_updated.state == ApprovalState.APPROVED
    assert fetched_updated.decided_by == "admin"


def test_approval_store_mark_expired(store):
    now = time.time()
    req_expired = ApprovalRequest(
        approval_id="app-old",
        request_id="req-old",
        principal_id="user",
        tool_name="RunPCCommandTool",
        action="execute",
        arguments={},
        raw_arguments_hash="hash",
        resource_scope="system",
        permission="tool.execute",
        risk_level=RiskLevel.T3,
        reason="Testing",
        created_at=now - 200,
        expires_at=now - 50,  # Expired
        state=ApprovalState.PENDING
    )
    store.store_request(req_expired)

    count = store.mark_expired()
    assert count == 1

    fetched = store.get_request("app-old")
    assert fetched.state == ApprovalState.EXPIRED

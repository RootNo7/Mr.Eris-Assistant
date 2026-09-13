import time
import pytest
from backend.tools.base import BaseTool
from backend.security.enums import RiskLevel, PolicyDecision, SecurityMode, ApprovalState
from backend.security.policy import PolicyEngine
from backend.security.engine import PermissionEngine
from backend.security.approval import ApprovalManager
from backend.security.executor import CentralToolExecutor
from backend.storage.approval_store import ApprovalStore


class MockDestructiveTool(BaseTool):
    name = "destructive_tool"
    description = "Mock destructive T3 operation requiring approval"
    risk_level = RiskLevel.T3
    requires_approval = True
    permission_scope = "system"
    required_permission = "system.admin"

    def execute(self, action_type: str = "run") -> str:
        return f"Executed destructive action '{action_type}'"

    def get_schema(self):
        def schema_fn(action_type: str = "run"):
            pass
        return schema_fn


@pytest.fixture
def test_setup(tmp_path):
    db_file = tmp_path / "test_reval.db"
    store = ApprovalStore(db_path=str(db_file))
    mgr = ApprovalManager(store=store, default_ttl_seconds=10.0)
    policy = PolicyEngine(mode=SecurityMode.BALANCED)
    executor = CentralToolExecutor(policy_engine=policy, approval_manager=mgr)
    tool = MockDestructiveTool()
    yield {
        "store": store,
        "manager": mgr,
        "policy": policy,
        "executor": executor,
        "tool": tool
    }
    store.clear()


def test_approval_policy_change_denial(test_setup):
    """
    SECURITY TEST: Approval + Policy Change to DENY -> Execution MUST be DENIED.
    APPROVAL + DENIED POLICY = DENIED
    """
    executor = test_setup["executor"]
    policy = test_setup["policy"]
    mgr = test_setup["manager"]
    tool = test_setup["tool"]

    # 1. First execution attempt returns REQUIRE_APPROVAL notification with approval_id
    res1 = executor.execute(tool=tool, kwargs={"action_type": "delete_all"})
    assert "[SECURITY APPROVAL REQUIRED]" in res1

    # Extract approval_id from response
    pending_list = mgr.list_pending()
    assert len(pending_list) == 1
    app_id = pending_list[0].approval_id

    # 2. User approves request
    mgr.approve(app_id, decided_by="admin")

    # 3. Policy is changed to STRICT posture where T3 is DENIED
    policy.mode = SecurityMode.STRICT

    # 4. Execution attempted with approved approval_id
    res2 = executor.execute(tool=tool, kwargs={"action_type": "delete_all"}, approval_id=app_id)

    # 5. Execution MUST fail despite user approval because policy is now DENY
    assert "[SECURITY DENIAL]" in res2
    assert "APPROVAL_EXECUTION_BLOCKED" in res2 or "denied by security policy" in res2.lower()


def test_approval_argument_mutation_denial(test_setup):
    """
    SECURITY TEST: Argument or scope mutation post-approval -> Execution MUST be DENIED due to binding mismatch.
    """
    executor = test_setup["executor"]
    mgr = test_setup["manager"]
    tool = test_setup["tool"]

    # 1. Request approval for safe command
    res1 = executor.execute(tool=tool, kwargs={"action_type": "safe_check"})
    pending_list = mgr.list_pending()
    app_id = pending_list[0].approval_id

    # 2. User approves "safe_check"
    mgr.approve(app_id, decided_by="user")

    # 3. Attacker attempts execution using same approval_id but mutated payload ("destroy")
    res_mutated = executor.execute(tool=tool, kwargs={"action_type": "destroy"}, approval_id=app_id)

    # 4. Must be denied due to binding mismatch
    assert "[SECURITY DENIAL]" in res_mutated
    assert "binding mismatch" in res_mutated.lower()


def test_approval_replay_protection(test_setup):
    """
    SECURITY TEST: Single-use replay protection -> Re-executing an approved request MUST be DENIED.
    After a successful execution the request transitions to state 'executed'; any subsequent
    attempt with the same approval_id must be denied.
    """
    executor = test_setup["executor"]
    mgr = test_setup["manager"]
    tool = test_setup["tool"]

    res1 = executor.execute(tool=tool, kwargs={"action_type": "run"})
    assert "[SECURITY APPROVAL REQUIRED]" in res1
    pending_list = mgr.list_pending()
    assert len(pending_list) == 1
    app_id = pending_list[0].approval_id

    mgr.approve(app_id, decided_by="user")

    # First execution succeeds
    first_run = executor.execute(tool=tool, kwargs={"action_type": "run"}, approval_id=app_id)
    assert "Executed destructive action 'run'" in first_run

    # Second execution using SAME approval_id MUST be denied (replay protection).
    # The request state is 'executed' after the first run; the denial message reflects that.
    second_run = executor.execute(tool=tool, kwargs={"action_type": "run"}, approval_id=app_id)
    assert "[SECURITY DENIAL]" in second_run
    # The denial must reference the executed-state or approval_id (proof of replay block)
    assert "executed" in second_run.lower() or app_id in second_run


def test_expired_approval_execution_denial(test_setup):
    """
    SECURITY TEST: Executing an expired approval request MUST be DENIED.

    Design note: We use a 1-second TTL and retrieve the approval_id directly from
    create_request() rather than list_pending().  list_pending() calls mark_expired()
    internally, which would sweep and remove very short-lived (0.1 s) pending entries
    before we can read their IDs.  We approve the request while it is still valid, then
    sleep past the TTL so the executor's is_expired check triggers the denial.
    """
    executor = test_setup["executor"]
    store = test_setup["store"]
    mgr = ApprovalManager(store=store, default_ttl_seconds=1.0)
    executor.approval_manager = mgr
    tool = test_setup["tool"]

    # Create request and capture the approval_id directly (avoids list_pending() sweep)
    req = mgr.create_request(
        tool_name=tool.name,
        risk_level=tool.risk_level,
        args={"action_type": "run"},
        scope=tool.permission_scope,
        required_permission=tool.required_permission,
    )
    app_id = req.approval_id

    # Approve while still within the TTL window
    mgr.approve(app_id, decided_by="user")

    time.sleep(1.05)  # Wait past 1-second TTL

    # Executor must deny because the approval is past its expiry
    res_expired = executor.execute(tool=tool, kwargs={"action_type": "run"}, approval_id=app_id)
    assert "[SECURITY DENIAL]" in res_expired
    assert "expired" in res_expired.lower()

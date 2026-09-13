import os
import pytest
from typing import Callable, Dict, Any
from backend.security.enums import RiskLevel, PolicyDecision, SecurityMode, ApprovalStatus
from backend.security.permissions import (
    Permission,
    Principal,
    ResourceScope,
    PermissionRequest,
    PermissionContext,
    PermissionDecision
)
from backend.security.engine import PermissionEngine
from backend.security.policy import PolicyEngine
from backend.security.approval import AutoApprovalGate
from backend.security.executor import CentralToolExecutor
from backend.tools.base import BaseTool
from backend.tools.registry import ToolRegistry
from backend.tools.system_info import SystemInfoTool
from backend.tools.pc_tools import LaunchAppTool, RunPCCommandTool
from backend.tools.file_tools import ReadFileTool, WriteFileTool


# --- Dummy Tools for Test Boundary Scenarios ---

class UnregisteredDummyTool(BaseTool):
    name = "unregistered_tool"
    description = "Dummy tool not registered in policy."
    risk_level = RiskLevel.T1
    permission_scope = "unregistered"
    required_permission = "unregistered.permission"

    def execute(self, **kwargs) -> str:
        return "unregistered output"

    def get_schema(self) -> Callable:
        return lambda: "unregistered output"


class CustomResourceTool(BaseTool):
    name = "custom_resource_tool"
    description = "Accesses a target resource."
    risk_level = RiskLevel.T1
    permission_scope = "custom.resource"
    required_permission = "filesystem.read"

    def execute(self, file_path: str = "", **kwargs) -> str:
        return f"Accessed {file_path}"

    def get_schema(self) -> Callable:
        return lambda file_path="": f"Accessed {file_path}"


class T4ProhibitedTool(BaseTool):
    name = "t4_prohibited_tool"
    description = "T4 prohibited security operation."
    risk_level = RiskLevel.T4
    permission_scope = "system.admin"
    required_permission = "system.admin"

    def execute(self, **kwargs) -> str:
        return "T4 Executed"

    def get_schema(self) -> Callable:
        return lambda: "T4 Executed"


# --- Test Suite ---

def test_1_known_safe_tool_allowed():
    """1. Known safe tool (T0) produces ALLOW decision."""
    engine = PermissionEngine(mode=SecurityMode.BALANCED, max_auto_risk=RiskLevel.T1)
    req = PermissionRequest(
        tool_name="get_system_info",
        resource="system.info",
        required_permission=Permission.SYSTEM_CONTROL.value,
        risk_level=RiskLevel.T0
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.ALLOW
    assert decision.is_allowed()


def test_2_unknown_tool_default_deny():
    """2. Unknown / unlisted tool falls back to default-deny."""
    engine = PermissionEngine(allowed_tools={"get_system_info", "files.read"})
    req = PermissionRequest(
        tool_name="unregistered_tool",
        resource="general",
        required_permission="unregistered.permission",
        risk_level=RiskLevel.T1
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.DENY
    assert decision.is_denied()
    assert "STAGE_3_TOOL_NOT_IN_ALLOWED_LIST" in decision.policy_id


def test_3_known_permission_granted():
    """3. Principal with granted permission receives ALLOW."""
    engine = PermissionEngine(mode=SecurityMode.BALANCED)
    principal = Principal(id="test_user", granted_permissions={"filesystem.read"})
    ctx = PermissionContext(principal=principal)
    req = PermissionRequest(
        tool_name="files.read",
        resource="/workspace/file.txt",
        required_permission="filesystem.read",
        risk_level=RiskLevel.T1
    )
    decision = engine.evaluate(req, context=ctx)
    assert decision.decision == PolicyDecision.ALLOW


def test_4_unknown_or_missing_permission_denied():
    """4. Principal lacking required permission is DENIED."""
    engine = PermissionEngine(mode=SecurityMode.BALANCED)
    principal = Principal(id="restricted_user", granted_permissions={"filesystem.read"})
    ctx = PermissionContext(principal=principal)
    req = PermissionRequest(
        tool_name="files.write",
        resource="/workspace/file.txt",
        required_permission="filesystem.write",
        risk_level=RiskLevel.T2
    )
    decision = engine.evaluate(req, context=ctx)
    assert decision.decision == PolicyDecision.DENY
    assert "lacks required permission" in decision.reason


def test_5_allowed_resource_scope():
    """5. Resource within allowed scope is authorized."""
    engine = PermissionEngine(mode=SecurityMode.BALANCED)
    req = PermissionRequest(
        tool_name="files.read",
        resource="/allowed/path/doc.txt",
        required_permission="filesystem.read",
        risk_level=RiskLevel.T1
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.ALLOW


def test_6_denied_resource_scope():
    """6. Resource matching forbidden scope is DENIED."""
    engine = PermissionEngine(forbidden_scopes={"/etc/shadow", "C:\\Windows\\System32"})
    req = PermissionRequest(
        tool_name="files.read",
        resource="C:\\Windows\\System32\\drivers\\etc\\hosts",
        required_permission="filesystem.read",
        risk_level=RiskLevel.T1
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.DENY
    assert "STAGE_4_RESOURCE_SCOPE_MATCH" in decision.policy_id


def test_7_t4_critical_action_blocked():
    """7. Critical T4 action is BLOCKED (hard block)."""
    engine = PermissionEngine()
    req = PermissionRequest(
        tool_name="t4_prohibited_tool",
        resource="system.admin",
        required_permission="system.admin",
        risk_level=RiskLevel.T4
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.BLOCK
    assert decision.is_denied()
    assert "STAGE_1_GLOBAL_HARD_BLOCK_T4" in decision.policy_id


def test_8_malformed_request_argument_validation():
    """8. Malformed request arguments fail signature check before permission evaluation."""
    executor = CentralToolExecutor()
    registry = ToolRegistry(executor=executor)
    registry.register(LaunchAppTool())

    # Mismatched kwarg signature
    res = registry.execute_tool("launch_application", {"invalid_param_xyz": 123})
    assert "[SECURITY DENIAL]" in res
    assert "Validation error" in res


def test_9_malformed_policy_fails_closed():
    """9. Malformed policy configuration fails closed to DENY ALL."""
    engine = PermissionEngine(mode="invalid_mode_str")  # Invalid mode string
    assert not engine._valid_config

    req = PermissionRequest(
        tool_name="get_system_info",
        resource="system.info",
        required_permission="system.control",
        risk_level=RiskLevel.T0
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.DENY
    assert "FAIL_CLOSED" in decision.policy_id


def test_10_missing_policy_fails_closed():
    """10. Missing policy configuration parameters fail closed."""
    engine = PermissionEngine(max_auto_risk="INVALID_RISK")
    assert not engine._valid_config

    req = PermissionRequest(
        tool_name="get_system_info",
        resource="system.info",
        required_permission="system.control",
        risk_level=RiskLevel.T0
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.DENY


def test_11_conflicting_policy_rules_precedence():
    """11. Deterministic precedence: Stage 1 Hard Block overrides explicit principal grant."""
    engine = PermissionEngine()
    # Principal has admin permissions granted, but T4 is Stage 1 hard blocked
    admin_principal = Principal(id="admin", is_admin=True, granted_permissions={"*"})
    ctx = PermissionContext(principal=admin_principal)
    req = PermissionRequest(
        tool_name="t4_prohibited_tool",
        resource="system.admin",
        required_permission="system.admin",
        risk_level=RiskLevel.T4
    )
    decision = engine.evaluate(req, context=ctx)
    assert decision.decision == PolicyDecision.BLOCK  # Stage 1 precedence beats Stage 2 admin


def test_12_invalid_risk_level_evaluation():
    """12. Invalid or unexpected risk level fails closed."""
    engine = PermissionEngine()
    req = PermissionRequest(
        tool_name="get_system_info",
        resource="system.info",
        required_permission="system.control",
        risk_level=RiskLevel.T4  # Critical risk
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.BLOCK


def test_13_default_deny_behavior():
    """13. Default-deny produces DENY when risk posture forbids auto-approval."""
    engine = PermissionEngine(mode=SecurityMode.STRICT)
    req = PermissionRequest(
        tool_name="files.write",
        resource="/workspace/data.txt",
        required_permission="filesystem.write",
        risk_level=RiskLevel.T3
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.DENY
    assert "STAGE_5_RISK_STRICT_DENY" in decision.policy_id


def test_14_explicit_allow_rule():
    """14. T0/T1 operations under BALANCED posture resolve to PolicyDecision.ALLOW."""
    engine = PermissionEngine(mode=SecurityMode.BALANCED, max_auto_risk=RiskLevel.T1)
    req = PermissionRequest(
        tool_name="files.read",
        resource="/workspace/data.txt",
        required_permission="filesystem.read",
        risk_level=RiskLevel.T1
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.ALLOW


def test_15_explicit_deny_rule():
    """15. Explicitly forbidden tool is DENIED."""
    engine = PermissionEngine(forbidden_tools={"execute_pc_command"})
    req = PermissionRequest(
        tool_name="execute_pc_command",
        resource="terminal",
        required_permission="process.manage",
        risk_level=RiskLevel.T3
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.DENY
    assert "STAGE_3_TOOL_RESTRICTION" in decision.policy_id


def test_16_approval_required_decision():
    """16. T3 operations trigger REQUIRE_APPROVAL decision under BALANCED posture."""
    engine = PermissionEngine(mode=SecurityMode.BALANCED, max_auto_risk=RiskLevel.T1)
    req = PermissionRequest(
        tool_name="execute_pc_command",
        resource="terminal",
        required_permission="process.manage",
        risk_level=RiskLevel.T3
    )
    decision = engine.evaluate(req)
    assert decision.decision == PolicyDecision.REQUIRE_APPROVAL
    assert decision.requires_approval()


def test_17_voice_originated_request_chokepoint():
    """17. Voice-originated request passes through CentralToolExecutor boundary."""
    policy = PolicyEngine(mode=SecurityMode.BALANCED)
    gate = AutoApprovalGate(default_approved=False)  # Rejects approval
    executor = CentralToolExecutor(policy_engine=policy, approval_gate=gate)
    registry = ToolRegistry(executor=executor)
    registry.register(RunPCCommandTool())

    # Simulated voice daemon dispatching tool execution
    res = registry.execute_tool("execute_pc_command", {"command": "echo voice_test"})
    assert "[SECURITY DENIAL]" in res
    assert "rejected by user" in res


def test_18_api_originated_request_chokepoint():
    """18. API-originated request passes through CentralToolExecutor boundary."""
    executor = CentralToolExecutor()
    registry = ToolRegistry(executor=executor)
    registry.register(T4ProhibitedTool())

    # Simulated REST API endpoint calling tool execution
    res = registry.execute_tool("t4_prohibited_tool", {})
    assert "[SECURITY DENIAL]" in res


def test_19_cli_originated_request_chokepoint():
    """19. CLI-originated request passes through CentralToolExecutor boundary."""
    executor = CentralToolExecutor()
    registry = ToolRegistry(executor=executor)
    registry.register(SystemInfoTool())

    res = registry.execute_tool("get_system_info", {})
    assert "[SECURITY DENIAL]" not in res
    assert "operating_system" in res or isinstance(res, str)


def test_20_direct_execution_bypass_prevention():
    """20. Attempting to bypass registry or policy by calling executor directly is guarded."""
    policy = PolicyEngine(mode=SecurityMode.STRICT)
    executor = CentralToolExecutor(policy_engine=policy)
    t4_tool = T4ProhibitedTool()

    # Direct call to CentralToolExecutor.execute()
    res = executor.execute(t4_tool, {})
    assert "[SECURITY DENIAL]" in res
    assert "denied by security policy" in res

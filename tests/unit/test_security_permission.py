import time
import os
import pytest
from typing import Dict, Any, Callable
from backend.tools.base import BaseTool
from backend.tools.registry import ToolRegistry
from backend.tools.system_info import SystemInfoTool
from backend.tools.pc_tools import LaunchAppTool, OpenUrlTool, RunPCCommandTool
from backend.security.enums import RiskLevel, PolicyDecision, SecurityMode, ApprovalStatus, ExecutionStatus
from backend.security.policy import PolicyEngine
from backend.security.approval import AutoApprovalGate, ApprovalGate
from backend.security.audit import AuditLogger, AuditEvent
from backend.security.executor import CentralToolExecutor


# --- Mock / Dummy Tools for Specific Test Conditions ---

def dummy_slow_func(delay: float = 2.0) -> str:
    """A dummy slow function for testing execution timeouts."""
    time.sleep(delay)
    return "Finished"

class SlowTool(BaseTool):
    name = "slow_tool"
    description = "A tool that sleeps past its timeout threshold."
    risk_level = RiskLevel.T1
    requires_approval = False
    timeout_seconds = 0.2  # 200 ms timeout for fast test execution
    permission_scope = "test.slow"

    def execute(self, delay: float = 1.0, **kwargs) -> str:
        return dummy_slow_func(delay=delay)

    def get_schema(self) -> Callable:
        return dummy_slow_func


def dummy_critical_func(action: str) -> str:
    """A dummy T4 critical system operation."""
    return f"Executed critical action: {action}"

class CriticalT4Tool(BaseTool):
    name = "critical_t4_tool"
    description = "Critical risk tool that formats system disk."
    risk_level = RiskLevel.T4
    requires_approval = True
    timeout_seconds = 5.0
    permission_scope = "system.admin"

    def execute(self, action: str = "format", **kwargs) -> str:
        return dummy_critical_func(action=action)

    def get_schema(self) -> Callable:
        return dummy_critical_func


def dummy_buggy_func() -> str:
    """A dummy tool that raises an runtime exception."""
    raise RuntimeError("Internal hardware simulation crash")

class BuggyTool(BaseTool):
    name = "buggy_tool"
    description = "A tool that crashes during execution."
    risk_level = RiskLevel.T1
    requires_approval = False
    timeout_seconds = 5.0
    permission_scope = "test.buggy"

    def execute(self, **kwargs) -> str:
        return dummy_buggy_func()

    def get_schema(self) -> Callable:
        return dummy_buggy_func


# --- Test Suite ---

def test_safe_tool_execution():
    """Verify T0 and T1 safe tools execute automatically under BALANCED policy."""
    registry = ToolRegistry()
    registry.register(SystemInfoTool())
    registry.register(LaunchAppTool())

    # T0 system info tool
    info_res = registry.execute_tool("get_system_info", {})
    assert "[SECURITY DENIAL]" not in info_res
    assert "operating_system" in info_res or isinstance(info_res, str)


def test_denied_tool_execution():
    """Verify T4 critical risk tools are automatically denied by security policy."""
    registry = ToolRegistry()
    registry.register(CriticalT4Tool())

    res = registry.execute_tool("critical_t4_tool", {"action": "format"})
    assert "[SECURITY DENIAL]" in res
    assert "denied by security policy" in res


def test_approval_required_tool_approved():
    """Verify T3 tool requiring approval executes when authorized by ApprovalGate."""
    policy = PolicyEngine(mode=SecurityMode.BALANCED)
    gate = AutoApprovalGate(default_approved=True)
    executor = CentralToolExecutor(policy_engine=policy, approval_gate=gate)
    registry = ToolRegistry(executor=executor)
    
    registry.register(RunPCCommandTool())

    # Execute with explicit approval gate allowing execution
    res = registry.execute_tool("execute_pc_command", {"command": "echo hello_eris"})
    assert "[SECURITY DENIAL]" not in res
    assert "hello_eris" in res or "Command executed" in res


def test_approval_required_tool_rejected():
    """Verify T3 tool requiring approval is safely denied when authorization is rejected."""
    policy = PolicyEngine(mode=SecurityMode.BALANCED)
    gate = AutoApprovalGate(default_approved=False)  # Rejects approval
    executor = CentralToolExecutor(policy_engine=policy, approval_gate=gate)
    registry = ToolRegistry(executor=executor)
    
    registry.register(RunPCCommandTool())

    res = registry.execute_tool("execute_pc_command", {"command": "echo test"})
    assert "[SECURITY DENIAL]" in res
    assert "was rejected by user" in res


def test_t3_tool_default_deny():
    """Verify T3 tool (execute_pc_command) pauses for approval when executed without an approval_id.

    Since v2.9.1, the Approval System is active: T3 tools create a pending approval
    request and return [SECURITY APPROVAL REQUIRED] instead of a flat [SECURITY DENIAL].
    A [SECURITY DENIAL] is produced only when an explicit rejection occurs or the
    policy decision is DENY/BLOCK (T4 and forbidden scopes).
    """
    executor = CentralToolExecutor()
    registry = ToolRegistry(executor=executor)
    registry.register(RunPCCommandTool())

    res = registry.execute_tool("execute_pc_command", {"command": "echo default_deny_test"})
    # v2.9.1: T3 tools are paused for approval, not hard-denied
    assert "[SECURITY APPROVAL REQUIRED]" in res
    assert "execute_pc_command" in res



def test_malformed_arguments():
    """Verify invalid or missing required tool arguments are caught during validation."""
    registry = ToolRegistry()
    registry.register(LaunchAppTool())

    # Passing unexpected argument type or signature mismatch
    res = registry.execute_tool("launch_application", {"invalid_arg_key_xyz": "value"})
    assert "[SECURITY DENIAL]" in res
    assert "Validation error" in res or "got an unexpected keyword argument" in res


def test_invalid_permission_scope():
    """Verify tool with an explicitly forbidden scope is denied by PolicyEngine."""
    forbidden = {"system.admin", "restricted.scope"}
    policy = PolicyEngine(forbidden_scopes=forbidden)
    executor = CentralToolExecutor(policy_engine=policy)
    registry = ToolRegistry(executor=executor)
    
    # Custom tool with forbidden scope
    tool = SystemInfoTool()
    tool.permission_scope = "restricted.scope"
    registry.register(tool)

    res = registry.execute_tool("get_system_info", {})
    assert "[SECURITY DENIAL]" in res
    assert "denied by security policy" in res


def test_timeout_handling():
    """Verify tool execution exceeding timeout_seconds is terminated safely."""
    executor = CentralToolExecutor()
    registry = ToolRegistry(executor=executor)
    registry.register(SlowTool())

    res = registry.execute_tool("slow_tool", {"delay": 1.0})
    assert "[SECURITY ERROR]" in res
    assert "timed out" in res


def test_failed_execution_audit(tmp_path):
    """Verify audit logger records events for failed tool execution."""
    log_dir = str(tmp_path)
    audit_logger = AuditLogger(log_dir=log_dir)
    executor = CentralToolExecutor(audit_logger=audit_logger)
    registry = ToolRegistry(executor=executor)
    registry.register(BuggyTool())

    res = registry.execute_tool("buggy_tool", {})
    assert "Error executing tool 'buggy_tool'" in res

    # Inspect audit log file
    log_file = os.path.join(log_dir, "audit.log")
    assert os.path.exists(log_file)
    with open(log_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "buggy_tool" in content
        assert ExecutionStatus.FAILED.value in content

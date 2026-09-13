"""
tests/unit/test_orchestration.py

Unit tests for ERIS v2.6.0 Orchestration Loop.

Tests use mock providers (no real AI API calls) so the suite is fast,
deterministic, and runs completely offline.

Test inventory:
    1.  test_one_step_task              — goal answered in one step, no tools
    2.  test_multi_step_task            — goal requiring two sequential tool calls
    3.  test_failed_tool_step           — tool raises error; loop records failure and continues
    4.  test_repeated_tool              — same tool called twice (distinct args)
    5.  test_timeout_breaker            — wall-clock limit triggers TIMED_OUT
    6.  test_step_count_breaker         — max_steps reached → LOOP_BREAKER
    7.  test_tool_call_count_breaker    — max_tool_calls reached → LOOP_BREAKER
    8.  test_approval_pause_auto        — T3 tool goes through approval gate (approved path)
    9.  test_cancellation               — cancel() called; task ends as CANCELLED
    10. test_security_denial_continues  — T4 tool denied; loop records denial and continues
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from backend.core.exceptions import (
    OrchestrationCancelledError,
    OrchestrationLoopBreakerError,
    OrchestrationTimeoutError,
)
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.loop import OrchestrationLoop
from backend.orchestration.models import TaskStatus, ToolObservation
from backend.security.approval import AutoApprovalGate
from backend.security.enums import RiskLevel
from backend.tools.base import BaseTool
from backend.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Helpers: Mock Provider
# ---------------------------------------------------------------------------

class MockProvider:
    """
    A deterministic mock AI provider that returns a pre-programmed sequence
    of (thought, tool_call_intent | None) tuples.

    When the sequence is exhausted, every subsequent call returns the
    fallback_final response (a plain final answer with no tool call).
    """

    def __init__(
        self,
        steps: List[Tuple[str, Optional[Dict[str, Any]]]],
        fallback_final: str = "Task complete.",
    ) -> None:
        self._steps = list(steps)
        self._index = 0
        self._fallback_final = fallback_final

    def generate_step(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        if self._index < len(self._steps):
            result = self._steps[self._index]
            self._index += 1
            return result
        return self._fallback_final, None

    # generate_response is required by the ABC but unused in orchestration tests
    def generate_response(self, prompt: str, history=None) -> str:  # type: ignore[override]
        thought, _ = self.generate_step(prompt=prompt, history=history)
        return thought


# ---------------------------------------------------------------------------
# Helpers: Mock Tools
# ---------------------------------------------------------------------------

def _make_echo_tool(name: str = "echo_tool", risk: RiskLevel = RiskLevel.T1) -> BaseTool:
    """Creates a simple echo tool that returns its input as a string."""

    class _EchoTool(BaseTool):
        pass

    def _echo_schema(message: str = "hello") -> str:  # type: ignore[return]
        """Echo a message."""
        ...

    _EchoTool.name = name
    _EchoTool.description = f"Echo tool ({name})"
    _EchoTool.risk_level = risk
    _EchoTool.requires_approval = (risk >= RiskLevel.T3)
    _EchoTool.timeout_seconds = 5.0
    _EchoTool.permission_scope = "test.echo"

    class _Inst(_EchoTool):
        def execute(self, message: str = "hello", **kwargs) -> str:
            return f"ECHO: {message}"

        def get_schema(self) -> Callable:
            return _echo_schema

    return _Inst()


def _make_crashing_tool(name: str = "crash_tool") -> BaseTool:
    """Creates a tool that raises an exception during execution."""

    def _crash_schema() -> str:  # type: ignore[return]
        """Crash tool."""
        ...

    class _CrashTool(BaseTool):
        pass

    _CrashTool.name = name
    _CrashTool.description = "Crash tool"
    _CrashTool.risk_level = RiskLevel.T1
    _CrashTool.requires_approval = False
    _CrashTool.timeout_seconds = 5.0
    _CrashTool.permission_scope = "test.crash"

    class _Inst(_CrashTool):
        def execute(self, **kwargs) -> str:
            raise RuntimeError("Simulated tool crash")

        def get_schema(self) -> Callable:
            return _crash_schema

    return _Inst()


def _make_critical_tool(name: str = "critical_t4") -> BaseTool:
    """Creates a T4 tool that will always be denied by PolicyEngine."""

    def _crit_schema(action: str = "format") -> str:  # type: ignore[return]
        """Critical system action."""
        ...

    class _CritTool(BaseTool):
        pass

    _CritTool.name = name
    _CritTool.description = "Critical T4 tool"
    _CritTool.risk_level = RiskLevel.T4
    _CritTool.requires_approval = True
    _CritTool.timeout_seconds = 5.0
    _CritTool.permission_scope = "system.admin"

    class _Inst(_CritTool):
        def execute(self, action: str = "format", **kwargs) -> str:
            return f"Executed: {action}"

        def get_schema(self) -> Callable:
            return _crit_schema

    return _Inst()


def _build_registry(*tools: BaseTool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_one_step_task():
    """Goal answered in one step — provider returns a final answer immediately."""
    provider = MockProvider(steps=[
        ("The capital of France is Paris.", None),
    ])
    registry = _build_registry()
    config = OrchestrationConfig.for_testing()

    loop = OrchestrationLoop(provider=provider, tool_registry=registry, config=config)
    task = loop.run(goal="What is the capital of France?")

    assert task.status == TaskStatus.COMPLETED
    assert task.final_answer == "The capital of France is Paris."
    assert task.step_count == 1
    assert task.tool_call_count == 0
    assert len(task.steps) == 1
    assert task.steps[0].tool_name is None


def test_multi_step_task():
    """Goal requiring two sequential tool calls, then a final answer."""
    echo_tool = _make_echo_tool("echo_tool")
    registry = _build_registry(echo_tool)
    config = OrchestrationConfig.for_testing()

    provider = MockProvider(steps=[
        # Step 0: call echo_tool with 'hello'
        ("Calling echo_tool.", {"name": "echo_tool", "args": {"message": "hello"}}),
        # Step 1: call echo_tool again with 'world'
        ("Calling echo_tool again.", {"name": "echo_tool", "args": {"message": "world"}}),
        # Step 2: final answer
        ("I called echo_tool twice. Done.", None),
    ])

    loop = OrchestrationLoop(provider=provider, tool_registry=registry, config=config)
    task = loop.run(goal="Call echo_tool twice then summarise.")

    assert task.status == TaskStatus.COMPLETED
    assert task.tool_call_count == 2
    assert task.step_count == 3
    assert task.steps[0].is_tool_step()
    assert task.steps[1].is_tool_step()
    assert not task.steps[2].is_tool_step()
    assert task.final_answer == "I called echo_tool twice. Done."

    # Verify observations contain echo results
    obs_0 = task.steps[0].observation
    obs_1 = task.steps[1].observation
    assert obs_0 is not None and "ECHO: hello" in obs_0.result
    assert obs_1 is not None and "ECHO: world" in obs_1.result


def test_failed_tool_step():
    """Tool raises an error — orchestrator records failure in observation and continues."""
    crash_tool = _make_crashing_tool("crash_tool")
    echo_tool = _make_echo_tool("echo_tool")
    registry = _build_registry(crash_tool, echo_tool)
    config = OrchestrationConfig(
        max_steps=5,
        max_tool_calls=10,
        max_execution_seconds=10.0,
        max_retries=0,   # No retries — fail immediately
    )

    provider = MockProvider(steps=[
        # Step 0: call the crashing tool
        ("Trying crash_tool.", {"name": "crash_tool", "args": {}}),
        # Step 1: recover and call echo instead
        ("crash_tool failed. Calling echo_tool instead.", {"name": "echo_tool", "args": {"message": "recovery"}}),
        # Step 2: final answer
        ("Recovered after crash. Done.", None),
    ])

    loop = OrchestrationLoop(provider=provider, tool_registry=registry, config=config)
    task = loop.run(goal="Test crash recovery.")

    assert task.status == TaskStatus.COMPLETED
    assert task.tool_call_count == 2

    crash_obs = task.steps[0].observation
    assert crash_obs is not None
    assert crash_obs.is_error
    assert "Simulated tool crash" in crash_obs.result or "Error executing tool" in crash_obs.result


def test_repeated_tool():
    """Same tool called twice with distinct arguments — both recorded correctly."""
    echo_tool = _make_echo_tool("echo_tool")
    registry = _build_registry(echo_tool)
    config = OrchestrationConfig.for_testing()

    provider = MockProvider(steps=[
        ("First call.", {"name": "echo_tool", "args": {"message": "alpha"}}),
        ("Second call.", {"name": "echo_tool", "args": {"message": "beta"}}),
        ("All done.", None),
    ])

    loop = OrchestrationLoop(provider=provider, tool_registry=registry, config=config)
    task = loop.run(goal="Call echo_tool with alpha then beta.")

    assert task.status == TaskStatus.COMPLETED
    assert task.tool_call_count == 2

    assert task.steps[0].tool_args == {"message": "alpha"}
    assert task.steps[1].tool_args == {"message": "beta"}

    assert "ECHO: alpha" in task.steps[0].observation.result
    assert "ECHO: beta" in task.steps[1].observation.result


def test_timeout_breaker():
    """
    Wall-clock limit triggers TIMED_OUT status.

    Uses a provider step that sleeps past the max_execution_seconds limit.
    """
    # Provider that sleeps 2 seconds on every step call
    class _SlowProvider:
        def generate_step(self, prompt, history=None):
            time.sleep(5.5)
            return "I took a long time.", None

        def generate_response(self, prompt, history=None):
            return "slow"

    config = OrchestrationConfig(
        max_steps=5,
        max_tool_calls=10,
        max_execution_seconds=5.0,  # 5 second wall-clock limit
        max_retries=0,
    )

    registry = _build_registry()
    loop = OrchestrationLoop(
        provider=_SlowProvider(),
        tool_registry=registry,
        config=config,
    )

    start = time.time()
    task = loop.run(goal="Test timeout.")
    elapsed = time.time() - start

    assert task.status == TaskStatus.TIMED_OUT
    assert task.error is not None and "exceeded maximum execution time" in task.error
    # The timeout should fire within a reasonable margin
    assert elapsed < config.max_execution_seconds + 5.0


def test_step_count_breaker():
    """Max steps reached → task ends with LOOP_BREAKER status."""
    echo_tool = _make_echo_tool("echo_tool")
    registry = _build_registry(echo_tool)

    # Provider that always calls echo_tool and never produces a final answer
    class _InfiniteProvider:
        def generate_step(self, prompt, history=None):
            return "Calling echo_tool.", {"name": "echo_tool", "args": {"message": "loop"}}

        def generate_response(self, prompt, history=None):
            return "loop"

    config = OrchestrationConfig(
        max_steps=3,
        max_tool_calls=100,
        max_execution_seconds=30.0,
        max_retries=0,
    )

    loop = OrchestrationLoop(
        provider=_InfiniteProvider(),
        tool_registry=registry,
        config=config,
    )
    task = loop.run(goal="Loop forever.")

    assert task.status == TaskStatus.LOOP_BREAKER
    assert task.step_count == config.max_steps
    assert "maximum step count" in task.error


def test_tool_call_count_breaker():
    """Max tool calls reached independently of step count → LOOP_BREAKER."""
    echo_tool = _make_echo_tool("echo_tool")
    registry = _build_registry(echo_tool)

    class _InfiniteProvider:
        def generate_step(self, prompt, history=None):
            return "Calling echo_tool.", {"name": "echo_tool", "args": {"message": "loop"}}

        def generate_response(self, prompt, history=None):
            return "loop"

    config = OrchestrationConfig(
        max_steps=100,           # high step limit
        max_tool_calls=2,        # low tool call limit — this should fire first
        max_execution_seconds=30.0,
        max_retries=0,
    )

    loop = OrchestrationLoop(
        provider=_InfiniteProvider(),
        tool_registry=registry,
        config=config,
    )
    task = loop.run(goal="Hit the tool call limit.")

    assert task.status == TaskStatus.LOOP_BREAKER
    assert task.tool_call_count == config.max_tool_calls
    assert "maximum tool call count" in task.error


def test_approval_pause_auto():
    """
    T3 tool call with AutoApprovalGate — gate approves automatically.
    Task should complete, not pause indefinitely.
    """
    t3_tool = _make_echo_tool("t3_echo", risk=RiskLevel.T3)
    registry = _build_registry(t3_tool)
    gate = AutoApprovalGate(default_approved=True)

    provider = MockProvider(steps=[
        ("Calling T3 tool.", {"name": "t3_echo", "args": {"message": "high_risk_msg"}}),
        ("T3 call complete.", None),
    ])

    config = OrchestrationConfig.for_testing()
    loop = OrchestrationLoop(
        provider=provider,
        tool_registry=registry,
        config=config,
        approval_gate=gate,
    )
    task = loop.run(goal="Run a T3 tool.")

    assert task.status == TaskStatus.COMPLETED
    assert task.tool_call_count == 1
    obs = task.steps[0].observation
    assert obs is not None
    # Security policy in balanced mode with max_auto_risk=T1 requires approval for T3;
    # AutoApprovalGate approves → tool executes
    assert not obs.is_denial


def test_cancellation():
    """
    cancel() called before the first step — task ends with CANCELLED status.
    """
    class _SlowProvider:
        def generate_step(self, prompt, history=None):
            time.sleep(0.5)
            return "Answer.", None

        def generate_response(self, prompt, history=None):
            return "slow"

    cancel_event = threading.Event()
    config = OrchestrationConfig.for_testing()
    registry = _build_registry()

    loop = OrchestrationLoop(
        provider=_SlowProvider(),
        tool_registry=registry,
        config=config,
        cancel_event=cancel_event,
    )

    # Set the cancel event before run() so the loop sees it at its first governor check
    cancel_event.set()
    task = loop.run(goal="This should be cancelled.")

    assert task.status == TaskStatus.CANCELLED
    assert task.error is not None and "cancelled" in task.error.lower()


def test_security_denial_continues():
    """
    T4 tool is denied by PolicyEngine — orchestrator records the denial
    in the observation and continues the loop (does not raise).
    """
    t4_tool = _make_critical_tool("deny_me")
    echo_tool = _make_echo_tool("echo_tool")
    registry = _build_registry(t4_tool, echo_tool)

    provider = MockProvider(steps=[
        # Step 0: try T4 tool (will be denied)
        ("Trying T4 tool.", {"name": "deny_me", "args": {"action": "format"}}),
        # Step 1: fall back to echo
        ("T4 denied. Using echo_tool.", {"name": "echo_tool", "args": {"message": "fallback"}}),
        # Step 2: final answer
        ("T4 was denied but I recovered.", None),
    ])

    config = OrchestrationConfig.for_testing()
    loop = OrchestrationLoop(provider=provider, tool_registry=registry, config=config)
    task = loop.run(goal="Try T4 then fallback.")

    assert task.status == TaskStatus.COMPLETED

    # First step observation must record the denial
    denial_obs = task.steps[0].observation
    assert denial_obs is not None
    assert denial_obs.is_denial
    assert "[SECURITY DENIAL]" in denial_obs.result

    # Second step should have succeeded with echo
    echo_obs = task.steps[1].observation
    assert echo_obs is not None
    assert not echo_obs.is_denial
    assert "ECHO: fallback" in echo_obs.result


# ---------------------------------------------------------------------------
# Config Validation Tests
# ---------------------------------------------------------------------------


def test_orchestration_config_validates_limits():
    """OrchestrationConfig raises ConfigurationError for out-of-range values."""
    from backend.core.exceptions import ConfigurationError

    with pytest.raises(ConfigurationError, match="max_steps"):
        OrchestrationConfig(max_steps=0)

    with pytest.raises(ConfigurationError, match="max_steps"):
        OrchestrationConfig(max_steps=101)

    with pytest.raises(ConfigurationError, match="max_tool_calls"):
        OrchestrationConfig(max_tool_calls=0)

    with pytest.raises(ConfigurationError, match="max_execution_seconds"):
        OrchestrationConfig(max_execution_seconds=1.0)  # below minimum 5s

    with pytest.raises(ConfigurationError, match="max_retries"):
        OrchestrationConfig(max_retries=-1)


def test_orchestration_config_for_testing_is_valid():
    """OrchestrationConfig.for_testing() produces a valid, shorter-timeout config."""
    config = OrchestrationConfig.for_testing()
    assert config.max_steps == 5
    assert config.max_execution_seconds == 10.0
    assert config.max_retries == 1


# ---------------------------------------------------------------------------
# Model Tests
# ---------------------------------------------------------------------------


def test_tool_observation_context_string():
    """ToolObservation.to_context_string() formats correctly for prompt injection."""
    obs = ToolObservation(
        tool_name="echo_tool",
        args={"message": "hi"},
        result="ECHO: hi",
        step_index=2,
        execution_time_ms=12.5,
        is_denial=False,
        is_error=False,
    )
    ctx = obs.to_context_string()
    assert "echo_tool" in ctx
    assert "STEP: 2" in ctx
    assert "ECHO: hi" in ctx
    assert "OK" in ctx


def test_tool_observation_denial_tag():
    """ToolObservation with is_denial=True formats status as DENIED."""
    obs = ToolObservation(
        tool_name="deny_me",
        args={},
        result="[SECURITY DENIAL] ...",
        step_index=0,
        is_denial=True,
    )
    ctx = obs.to_context_string()
    assert "DENIED" in ctx


def test_orchestration_task_to_dict():
    """OrchestrationTask.to_dict() returns a JSON-serialisable structure."""
    from backend.orchestration.models import OrchestrationTask, TaskStatus
    task = OrchestrationTask(goal="test goal")
    task.finish(TaskStatus.COMPLETED, final_answer="answer")

    d = task.to_dict()
    assert d["status"] == "completed"
    assert d["final_answer"] == "answer"
    assert isinstance(d["steps"], list)
    assert isinstance(d["elapsed_seconds"], float)

"""
backend/orchestration/config.py

Governor configuration for the ERIS Orchestration Loop (v2.6.0).

OrchestrationConfig centralises all safety limits and behavioural knobs
for a single task run.  It is intentionally a plain dataclass — no
dependency on Config or environment variables — so callers (API layer,
CLI, tests) can construct it explicitly with validated values.

Safety contract (all limits are HARD — disabling to zero or infinity is
not permitted at this layer):
  - max_steps           : 1 … 100   (default 10)
  - max_tool_calls      : 1 … 200   (default 20)
  - max_execution_seconds: 5 … 600  (default 120)
  - max_retries         : 0 … 10    (default 3)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from backend.core.exceptions import ConfigurationError


# Absolute hard limits — no caller may exceed these regardless of config.
_ABSOLUTE_MAX_STEPS: int = 100
_ABSOLUTE_MAX_TOOL_CALLS: int = 200
_ABSOLUTE_MAX_SECONDS: float = 600.0
_ABSOLUTE_MIN_SECONDS: float = 5.0
_ABSOLUTE_MAX_RETRIES: int = 10


@dataclass
class OrchestrationConfig:
    """
    Configuration and safety governors for one OrchestrationLoop run.

    Parameters
    ----------
    max_steps : int
        Maximum number of think/act/observe iterations before the loop
        terminates with LOOP_BREAKER status.  Range: 1–100.
    max_tool_calls : int
        Maximum cumulative tool invocations across all steps.  Counted
        independently from max_steps so a single step with many tools
        cannot exhaust the step budget.  Range: 1–200.
    max_execution_seconds : float
        Wall-clock time limit for the entire task.  The loop checks this
        before every step.  Range: 5–600 seconds.
    max_retries : int
        Maximum consecutive retry attempts for a step that fails due to
        a recoverable error (e.g. tool timeout, transient provider error).
        Range: 0–10.
    enable_approval_pause : bool
        When True, the loop pauses (returns WAITING_APPROVAL) instead of
        immediately proceeding when a T3+ tool requires explicit approval.
        When False, the loop delegates entirely to the ApprovalGate
        without a loop-level pause.
    """
    max_steps: int = 10
    max_tool_calls: int = 20
    max_execution_seconds: float = 120.0
    max_retries: int = 3
    enable_approval_pause: bool = True

    def __post_init__(self) -> None:
        self._validate()

    def _validate(self) -> None:
        """Validates all governor values at construction time."""
        if not (1 <= self.max_steps <= _ABSOLUTE_MAX_STEPS):
            raise ConfigurationError(
                f"OrchestrationConfig.max_steps must be between 1 and {_ABSOLUTE_MAX_STEPS}; "
                f"got {self.max_steps}."
            )
        if not (1 <= self.max_tool_calls <= _ABSOLUTE_MAX_TOOL_CALLS):
            raise ConfigurationError(
                f"OrchestrationConfig.max_tool_calls must be between 1 and {_ABSOLUTE_MAX_TOOL_CALLS}; "
                f"got {self.max_tool_calls}."
            )
        if not (_ABSOLUTE_MIN_SECONDS <= self.max_execution_seconds <= _ABSOLUTE_MAX_SECONDS):
            raise ConfigurationError(
                f"OrchestrationConfig.max_execution_seconds must be between "
                f"{_ABSOLUTE_MIN_SECONDS} and {_ABSOLUTE_MAX_SECONDS}; "
                f"got {self.max_execution_seconds}."
            )
        if not (0 <= self.max_retries <= _ABSOLUTE_MAX_RETRIES):
            raise ConfigurationError(
                f"OrchestrationConfig.max_retries must be between 0 and {_ABSOLUTE_MAX_RETRIES}; "
                f"got {self.max_retries}."
            )

    @classmethod
    def default(cls) -> "OrchestrationConfig":
        """Returns the default configuration with standard safety limits."""
        return cls()

    @classmethod
    def for_testing(cls) -> "OrchestrationConfig":
        """
        Returns a fast configuration for unit tests.
        Shorter timeouts prevent test suite hangs.
        """
        return cls(
            max_steps=5,
            max_tool_calls=10,
            max_execution_seconds=10.0,
            max_retries=1,
            enable_approval_pause=True,
        )

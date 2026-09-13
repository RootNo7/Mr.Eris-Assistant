"""
backend/orchestration/models.py

Domain data structures for the ERIS Orchestration Layer (v2.6.0).

All classes are plain Python dataclasses — no external dependencies.
They are intentionally serialisation-friendly (all fields are JSON-safe
primitive types, lists, or None).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Status Enumerations
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    """
    Lifecycle status of a complete orchestration task.

    Terminal states: COMPLETED, FAILED, CANCELLED, TIMED_OUT, LOOP_BREAKER.
    """
    PENDING         = "pending"          # created, not yet started
    RUNNING         = "running"          # loop is executing
    WAITING_APPROVAL = "waiting_approval" # paused — awaiting human approval
    COMPLETED       = "completed"        # reached a final answer
    FAILED          = "failed"           # unrecoverable error
    CANCELLED       = "cancelled"        # cooperative cancellation requested
    TIMED_OUT       = "timed_out"        # wall-clock limit exceeded
    LOOP_BREAKER    = "loop_breaker"     # max_steps or max_tool_calls exceeded


class StepStatus(str, Enum):
    """Lifecycle status of a single orchestration step."""
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    SKIPPED   = "skipped"


# ---------------------------------------------------------------------------
# Tool Observation
# ---------------------------------------------------------------------------


@dataclass
class ToolObservation:
    """
    Structured record of a single tool execution within an orchestration step.

    Produced by OrchestrationLoop after calling ToolRegistry.execute_tool().
    The orchestrator uses this to build the next-step prompt context.
    """
    tool_name: str
    args: Dict[str, Any]
    result: str                  # serialised string result (or denial/error message)
    step_index: int
    execution_time_ms: float = 0.0
    is_denial: bool = False      # True when result starts with "[SECURITY DENIAL]"
    is_error: bool = False       # True when execution encountered a runtime error

    def to_context_string(self) -> str:
        """
        Formats this observation as a plain-text snippet suitable for
        injection into the next provider prompt as prior-step context.
        """
        status_tag = "DENIED" if self.is_denial else ("ERROR" if self.is_error else "OK")
        return (
            f"[TOOL: {self.tool_name} | STATUS: {status_tag} | "
            f"STEP: {self.step_index} | TIME: {self.execution_time_ms:.1f}ms]\n"
            f"Args: {self.args}\n"
            f"Result: {self.result}"
        )


# ---------------------------------------------------------------------------
# Orchestration Step
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationStep:
    """
    One complete think → act → observe iteration of the orchestration loop.

    A step may or may not involve a tool call:
    - If the model produces a final answer (no tool call intent), the step
      records the final text and the task moves to COMPLETED.
    - If the model indicates a tool call, `tool_name`, `tool_args`, and
      `observation` are populated after execution.
    """
    step_index: int
    thought: str                          # raw model output for this step
    timestamp: float = field(default_factory=time.time)
    status: StepStatus = StepStatus.PENDING

    # Tool call fields (None when step produced a final answer directly)
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    observation: Optional[ToolObservation] = None

    # Retry tracking
    retry_count: int = 0

    def is_tool_step(self) -> bool:
        """Returns True when this step contains a tool invocation."""
        return self.tool_name is not None


# ---------------------------------------------------------------------------
# Orchestration Task
# ---------------------------------------------------------------------------


@dataclass
class OrchestrationTask:
    """
    Complete record of a single orchestration run.

    Created by OrchestrationLoop.run() and returned to the caller when the
    loop reaches any terminal state (COMPLETED, FAILED, CANCELLED, TIMED_OUT,
    LOOP_BREAKER).
    """
    goal: str
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    status: TaskStatus = TaskStatus.PENDING
    steps: List[OrchestrationStep] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    final_answer: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Convenience counters (kept in sync by the loop)
    step_count: int = 0
    tool_call_count: int = 0

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed wall-clock seconds from task start to now (or end_time)."""
        end = self.end_time if self.end_time is not None else time.time()
        return end - self.start_time

    def finish(self, status: TaskStatus, final_answer: Optional[str] = None, error: Optional[str] = None) -> None:
        """Marks this task as terminal and records end time."""
        self.status = status
        self.end_time = time.time()
        if final_answer is not None:
            self.final_answer = final_answer
        if error is not None:
            self.error = error

    def to_dict(self) -> Dict[str, Any]:
        """Returns a JSON-serialisable dict for API responses and logging."""
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status.value,
            "step_count": self.step_count,
            "tool_call_count": self.tool_call_count,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
            "final_answer": self.final_answer,
            "error": self.error,
            "steps": [
                {
                    "step_index": s.step_index,
                    "status": s.status.value,
                    "thought": s.thought,
                    "tool_name": s.tool_name,
                    "tool_args": s.tool_args,
                    "observation": s.observation.to_context_string() if s.observation else None,
                    "retry_count": s.retry_count,
                    "timestamp": s.timestamp,
                }
                for s in self.steps
            ],
            "metadata": self.metadata,
        }

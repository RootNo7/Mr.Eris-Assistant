"""
backend/orchestration/loop.py

ERIS Orchestration Loop — v2.6.0

Converts a flat user goal into a structured, governed, single-agent
think → act → observe cycle:

    user goal
        → planning (provider generates thought + optional tool call intent)
        → controlled tool execution (through CentralToolExecutor)
        → structured observation (ToolObservation)
        → next step (loop continues with updated context)
        → verification (final answer or governor triggered)
        → OrchestrationTask (complete record returned to caller)

Security contracts:
    - ALL tool calls pass through ToolRegistry.execute_tool(), which routes
      through CentralToolExecutor → PolicyEngine → ApprovalGate → AuditLogger.
    - The orchestration loop NEVER calls tool.execute() directly.
    - Governors (max_steps, max_tool_calls, max_execution_seconds) are checked
      before EVERY step and cannot be disabled.
    - Cancellation is cooperative via threading.Event — never abrupt.

Provider interface:
    The loop calls provider.generate_step() if available (returns a
    (thought_text, tool_call_dict | None) tuple).  If the provider does
    not implement generate_step(), the loop falls back to generate_response()
    and treats the full text as a final answer (no-tool path).  This keeps
    the existing simple chat pipeline 100% compatible.

Tool call intent protocol:
    Providers signal tool call intent by including a structured JSON block
    in their response enclosed in the sentinel markers:

        <<TOOL_CALL>>
        {"name": "tool_name", "args": {"key": "value"}}
        <</TOOL_CALL>>

    The loop extracts and parses this block.  Any response without this
    block is treated as a final answer.

    This sentinel approach:
    - Works identically across Gemini, OpenRouter, and Ollama
    - Requires no SDK-specific parsing
    - Is explicit and easy to test
    - Cannot be confused with normal prose
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from backend.core.exceptions import (
    OrchestrationCancelledError,
    OrchestrationLoopBreakerError,
    OrchestrationTimeoutError,
)
from backend.core.logging.logger import logger
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.models import (
    OrchestrationStep,
    OrchestrationTask,
    StepStatus,
    TaskStatus,
    ToolObservation,
)
from backend.security.approval import ApprovalGate, AutoApprovalGate
from backend.tools.registry import ToolRegistry


# Sentinel regex — matches the <<TOOL_CALL>> ... <</TOOL_CALL>> block
_TOOL_CALL_RE = re.compile(
    r"<<TOOL_CALL>>\s*(\{.*?\})\s*<</TOOL_CALL>>",
    re.DOTALL | re.IGNORECASE,
)

# Orchestration system prompt addendum injected before each step
_ORCHESTRATION_SYSTEM_ADDENDUM = """
You are operating in ORCHESTRATION MODE.

When you need to call a tool, output EXACTLY this format (and nothing else):
<<TOOL_CALL>>
{"name": "<tool_name>", "args": {<key>: <value>, ...}}
<</TOOL_CALL>>

When you have gathered enough information and are ready to give a final answer,
output your answer directly WITHOUT any <<TOOL_CALL>> block.

Do NOT explain your reasoning in the same response as a tool call.
Do NOT produce multiple tool calls in one response — one at a time.
"""


class OrchestrationLoop:
    """
    Controlled single-agent orchestration loop.

    Parameters
    ----------
    provider : AIProvider
        Any ERIS AI provider (Gemini, OpenRouter, Ollama).
    tool_registry : ToolRegistry
        The fully initialised ToolRegistry (with all tools registered).
    config : OrchestrationConfig
        Safety governors for this run.  Defaults to OrchestrationConfig().
    approval_gate : ApprovalGate | None
        Override the approval gate.  Defaults to AutoApprovalGate(default_approved=True).
    cancel_event : threading.Event | None
        Callers set this event to cooperatively cancel a running task.
        The loop checks this before every step.
    """

    def __init__(
        self,
        provider: Any,                              # AIProvider (avoid circular import)
        tool_registry: ToolRegistry,
        config: Optional[OrchestrationConfig] = None,
        approval_gate: Optional[ApprovalGate] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> None:
        self.provider = provider
        self.tool_registry = tool_registry
        self.config = config or OrchestrationConfig.default()
        self.approval_gate = approval_gate or AutoApprovalGate(default_approved=False)
        self.cancel_event = cancel_event or threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        goal: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> OrchestrationTask:
        """
        Execute the orchestration loop for the given goal.

        Returns an OrchestrationTask in a terminal state.  Never raises —
        all errors are captured inside the task.

        Parameters
        ----------
        goal : str
            The user's goal or question.
        history : list[dict] | None
            Prior conversation history in [{role, text}] format.
        """
        task = OrchestrationTask(goal=goal)
        task.status = TaskStatus.RUNNING
        history = history or []

        logger.info(
            f"[Orchestration] Task {task.task_id[:8]} started. "
            f"Goal: {goal[:80]!r}  "
            f"Governors: steps={self.config.max_steps}, "
            f"tools={self.config.max_tool_calls}, "
            f"seconds={self.config.max_execution_seconds}"
        )

        try:
            self._execute_loop(task, history)
        except OrchestrationCancelledError:
            task.finish(TaskStatus.CANCELLED, error="Task cancelled by caller.")
            logger.info(f"[Orchestration] Task {task.task_id[:8]} CANCELLED.")
        except OrchestrationTimeoutError as exc:
            task.finish(TaskStatus.TIMED_OUT, error=str(exc))
            logger.warning(f"[Orchestration] Task {task.task_id[:8]} TIMED_OUT: {exc}")
        except OrchestrationLoopBreakerError as exc:
            task.finish(TaskStatus.LOOP_BREAKER, error=str(exc))
            logger.warning(f"[Orchestration] Task {task.task_id[:8]} LOOP_BREAKER: {exc}")
        except Exception as exc:  # noqa: BLE001
            task.finish(TaskStatus.FAILED, error=f"Unexpected orchestration error: {exc}")
            logger.error(f"[Orchestration] Task {task.task_id[:8]} FAILED: {exc}", exc_info=True)

        logger.info(
            f"[Orchestration] Task {task.task_id[:8]} finished. "
            f"Status={task.status.value}  Steps={task.step_count}  "
            f"Tools={task.tool_call_count}  Elapsed={task.elapsed_seconds:.2f}s"
        )
        return task

    def cancel(self) -> None:
        """
        Request cooperative cancellation of the running task.
        The loop will stop before the next step begins.
        """
        self.cancel_event.set()
        logger.info("[Orchestration] Cancellation signal sent.")

    # ------------------------------------------------------------------
    # Internal Loop
    # ------------------------------------------------------------------

    def _execute_loop(self, task: OrchestrationTask, history: List[Dict[str, str]]) -> None:
        """
        Core think → act → observe loop.  Raises orchestration exceptions
        when governors are tripped; caller (run()) catches and records them.
        """
        # Build the orchestration context — accumulated observations injected
        # into each subsequent prompt so the provider sees prior results.
        observation_context: List[str] = []

        while True:
            # --- Governor Checks (before every step) ---
            self._check_governors(task)

            # --- Cancellation Check ---
            if self.cancel_event.is_set():
                raise OrchestrationCancelledError("Cancellation event was set.")

            # --- Build Step Prompt ---
            step_prompt = self._build_step_prompt(task.goal, observation_context)

            # --- Provider Call ---
            step = OrchestrationStep(
                step_index=task.step_count,
                thought="",
                status=StepStatus.RUNNING,
            )
            task.steps.append(step)
            task.step_count += 1

            thought, tool_call_intent = self._call_provider(step_prompt, history)
            step.thought = thought

            # --- Check Governors (after provider call) ---
            self._check_governors(task)

            # --- No Tool Call → Final Answer ---
            if tool_call_intent is None:
                step.status = StepStatus.COMPLETED
                task.finish(TaskStatus.COMPLETED, final_answer=thought)
                logger.info(
                    f"[Orchestration] Step {step.step_index}: Final answer produced. "
                    f"({len(thought)} chars)"
                )
                return

            # --- Tool Call Intent Detected ---
            tool_name = tool_call_intent.get("name", "")
            tool_args = tool_call_intent.get("args", {})
            step.tool_name = tool_name
            step.tool_args = tool_args

            logger.info(
                f"[Orchestration] Step {step.step_index}: Tool call intent — "
                f"{tool_name}({tool_args})"
            )

            # --- Execute Tool Step (with retry) ---
            observation = self._execute_step_with_retry(task, step, tool_name, tool_args)
            step.observation = observation
            step.status = StepStatus.COMPLETED

            # Accumulate observation for next prompt
            observation_context.append(observation.to_context_string())

    # ------------------------------------------------------------------
    # Governor Enforcement
    # ------------------------------------------------------------------

    def _check_governors(self, task: OrchestrationTask) -> None:
        """
        Raises the appropriate exception if any safety limit is exceeded.
        Called before every step to guarantee no infinite loops.
        """
        # 1. Wall-clock timeout
        if task.elapsed_seconds >= self.config.max_execution_seconds:
            raise OrchestrationTimeoutError(
                f"Task exceeded maximum execution time of "
                f"{self.config.max_execution_seconds}s "
                f"(elapsed: {task.elapsed_seconds:.2f}s)."
            )

        # 2. Step count
        if task.step_count >= self.config.max_steps:
            raise OrchestrationLoopBreakerError(
                f"Task reached maximum step count of {self.config.max_steps}."
            )

        # 3. Tool call count
        if task.tool_call_count >= self.config.max_tool_calls:
            raise OrchestrationLoopBreakerError(
                f"Task reached maximum tool call count of {self.config.max_tool_calls}."
            )

    # ------------------------------------------------------------------
    # Provider Interaction
    # ------------------------------------------------------------------

    def _call_provider(
        self,
        prompt: str,
        history: List[Dict[str, str]],
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Calls the provider and returns (thought_text, tool_call_intent | None).

        Prefers provider.generate_step() when available; falls back to
        generate_response() and treats the full text as a final answer.
        """
        if hasattr(self.provider, "generate_step"):
            # Provider natively supports structured step generation
            return self.provider.generate_step(prompt=prompt, history=history)

        # Fallback: treat generate_response() output as raw text and parse it
        raw = self.provider.generate_response(prompt=prompt, history=history) or ""
        tool_call_intent = self._parse_tool_call_intent(raw)
        if tool_call_intent is not None:
            # Strip the <<TOOL_CALL>> block from the thought text
            clean_thought = _TOOL_CALL_RE.sub("", raw).strip()
            return clean_thought, tool_call_intent
        return raw, None

    @staticmethod
    def _parse_tool_call_intent(text: str) -> Optional[Dict[str, Any]]:
        """
        Extracts a tool call intent dict from a <<TOOL_CALL>>...</TOOL_CALL>> block.
        Returns None when no such block is present.
        """
        match = _TOOL_CALL_RE.search(text)
        if not match:
            return None
        try:
            payload = json.loads(match.group(1))
            if "name" not in payload:
                logger.warning("[Orchestration] Tool call block found but missing 'name' key.")
                return None
            if not isinstance(payload.get("args", {}), dict):
                logger.warning("[Orchestration] Tool call block 'args' is not a dict; defaulting to {}.")
                payload["args"] = {}
            return payload
        except json.JSONDecodeError as exc:
            logger.warning(f"[Orchestration] Failed to parse tool call JSON: {exc}")
            return None

    def _build_step_prompt(self, goal: str, observation_context: List[str]) -> str:
        """
        Constructs the prompt for the next provider step, injecting the
        orchestration addendum and all prior observations.
        """
        parts = [_ORCHESTRATION_SYSTEM_ADDENDUM.strip(), "", f"GOAL: {goal}"]

        if observation_context:
            parts.append("")
            parts.append("PRIOR TOOL OBSERVATIONS:")
            for obs in observation_context:
                parts.append(obs)
                parts.append("---")

        parts.append("")
        parts.append(
            "Based on the above, either call the next required tool "
            "OR provide your final answer."
        )
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Tool Execution (with Retry)
    # ------------------------------------------------------------------

    def _execute_step_with_retry(
        self,
        task: OrchestrationTask,
        step: OrchestrationStep,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> ToolObservation:
        """
        Executes a single tool call through the ToolRegistry security pipeline,
        with up to config.max_retries retry attempts for recoverable failures.

        Retry is attempted when:
            - result contains a timeout error message
            - result contains a transient runtime error (not a security denial)

        Security denials are never retried.
        """
        last_observation: Optional[ToolObservation] = None

        for attempt in range(self.config.max_retries + 1):
            step.retry_count = attempt
            t_start = time.time()

            # Route through the full security pipeline
            result = self.tool_registry.execute_tool(
                name=tool_name,
                kwargs=tool_args,
                approval_gate=self.approval_gate,
            )
            task.tool_call_count += 1

            elapsed_ms = (time.time() - t_start) * 1000.0
            is_denial = result.startswith("[SECURITY DENIAL]")
            is_timeout = "[SECURITY ERROR]" in result and "timed out" in result
            is_error = (
                not is_denial
                and not is_timeout
                and result.startswith("Error executing tool")
            )

            observation = ToolObservation(
                tool_name=tool_name,
                args=tool_args,
                result=result,
                step_index=step.step_index,
                execution_time_ms=elapsed_ms,
                is_denial=is_denial,
                is_error=is_error or is_timeout,
            )
            last_observation = observation

            if is_denial:
                # Security denials are never retried — they are policy decisions.
                logger.warning(
                    f"[Orchestration] Step {step.step_index}: "
                    f"Tool '{tool_name}' was DENIED — no retry."
                )
                break

            if not (is_error or is_timeout):
                # Successful execution
                logger.info(
                    f"[Orchestration] Step {step.step_index}: "
                    f"Tool '{tool_name}' OK in {elapsed_ms:.1f}ms."
                )
                break

            # Recoverable error — retry if budget allows
            if attempt < self.config.max_retries:
                logger.warning(
                    f"[Orchestration] Step {step.step_index}: "
                    f"Tool '{tool_name}' failed (attempt {attempt + 1}/"
                    f"{self.config.max_retries + 1}) — retrying. "
                    f"Result: {result[:120]}"
                )
            else:
                logger.error(
                    f"[Orchestration] Step {step.step_index}: "
                    f"Tool '{tool_name}' failed after {self.config.max_retries + 1} attempts."
                )

        return last_observation  # type: ignore[return-value]  # always set

import inspect
import time
import concurrent.futures
from typing import Dict, Any, Optional
from backend.tools.base import BaseTool
from backend.security.enums import RiskLevel, PolicyDecision, ApprovalStatus, ExecutionStatus, ApprovalState
from backend.security.policy import PolicyEngine
from backend.security.approval import ApprovalGate, AutoApprovalGate, ApprovalManager, SystemApprovalGate
from backend.security.approval_models import compute_raw_args_hash, compute_binding_hash
from backend.security.audit import AuditLogger, AuditEvent
from backend.core.logging.logger import logger
from backend.core.exceptions import ToolNotFoundError, ToolExecutionError


class CentralToolExecutor:
    """
    Central Execution Chokepoint for ALL ERIS tools across all AI providers.
    Enforces argument validation, risk policy evaluation, approval gating,
    pre-execution revalidation, timeout handling, audit logging, and safe denial responses.
    """

    def __init__(
        self,
        policy_engine: Optional[PolicyEngine] = None,
        approval_gate: Optional[ApprovalGate] = None,
        approval_manager: Optional[ApprovalManager] = None,
        audit_logger: Optional[AuditLogger] = None
    ):
        self.policy_engine = policy_engine or PolicyEngine()
        self.approval_manager = approval_manager or ApprovalManager()
        self.approval_gate = approval_gate or SystemApprovalGate(manager=self.approval_manager)
        self.audit_logger = audit_logger or AuditLogger()

    def execute(
        self,
        tool: BaseTool,
        kwargs: Dict[str, Any],
        custom_approval_gate: Optional[ApprovalGate] = None,
        approval_id: Optional[str] = None,
        principal_id: str = "user",
        session_id: Optional[str] = None
    ) -> str:
        """
        Executes a tool through the 8-stage security pipeline (v2.9.1).
        Returns a serializable string result or safe denial message.
        """
        start_time = time.time()
        tool_name = getattr(tool, "name", "unknown_tool")
        risk_level = getattr(tool, "risk_level", RiskLevel.T1)
        requires_approval = getattr(tool, "requires_approval", False)
        timeout_seconds = getattr(tool, "timeout_seconds", 10.0)
        permission_scope = getattr(tool, "permission_scope", "general")
        required_permission = getattr(tool, "required_permission", "tool.execute")
        gate = custom_approval_gate or self.approval_gate

        # 0. Tool Enabled Check
        if not getattr(tool, "enabled", True):
            execution_time_ms = (time.time() - start_time) * 1000.0
            error_msg = f"[SECURITY DENIAL] Tool '{tool_name}' is disabled."
            logger.warning(error_msg)
            self.audit_logger.record_event(AuditEvent(
                timestamp=start_time,
                tool_name=tool_name,
                risk_level=str(risk_level),
                permission_scope=permission_scope,
                args=kwargs,
                policy_decision=PolicyDecision.DENY.value,
                approval_status=ApprovalStatus.NOT_REQUIRED.value,
                execution_status=ExecutionStatus.DENIED.value,
                execution_time_ms=execution_time_ms,
                error_message="Tool is disabled"
            ))
            return error_msg

        # 1. Argument & Signature Validation
        try:
            fn = tool.get_schema()
            sig = inspect.signature(fn)
            bound_args = sig.bind(**kwargs)
            bound_args.apply_defaults()
        except TypeError as val_err:
            execution_time_ms = (time.time() - start_time) * 1000.0
            error_msg = f"Argument validation failed for '{tool_name}': {val_err}"
            logger.error(error_msg)
            
            self.audit_logger.record_event(AuditEvent(
                timestamp=start_time,
                tool_name=tool_name,
                risk_level=str(risk_level),
                permission_scope=permission_scope,
                args=kwargs,
                policy_decision=PolicyDecision.DENY.value,
                approval_status=ApprovalStatus.NOT_REQUIRED.value,
                execution_status=ExecutionStatus.VALIDATION_ERROR.value,
                execution_time_ms=execution_time_ms,
                error_message=error_msg
            ))
            return f"[SECURITY DENIAL] Validation error for tool '{tool_name}': {val_err}"

        # 2. Initial Policy Evaluation
        policy_decision = self.policy_engine.evaluate(
            tool_name=tool_name,
            risk_level=risk_level,
            requires_approval=requires_approval,
            scope=permission_scope,
            kwargs=kwargs,
            required_permission=required_permission
        )

        if policy_decision in (PolicyDecision.DENY, PolicyDecision.BLOCK):
            execution_time_ms = (time.time() - start_time) * 1000.0
            denial_msg = f"[SECURITY DENIAL] Execution of tool '{tool_name}' ({risk_level}) was denied by security policy."
            logger.warning(denial_msg)
            
            self.audit_logger.record_event(AuditEvent(
                timestamp=start_time,
                tool_name=tool_name,
                risk_level=str(risk_level),
                permission_scope=permission_scope,
                args=kwargs,
                policy_decision=policy_decision.value,
                approval_status=ApprovalStatus.NOT_REQUIRED.value,
                execution_status=ExecutionStatus.DENIED.value,
                execution_time_ms=execution_time_ms,
                error_message="Denied by policy"
            ))
            return denial_msg

        # 3. Approval Gate & Pre-Execution Revalidation (v2.9.1)
        approval_status = ApprovalStatus.NOT_REQUIRED
        if policy_decision == PolicyDecision.REQUIRE_APPROVAL:
            # If an explicit AutoApprovalGate is provided (e.g. in tests)
            if isinstance(gate, AutoApprovalGate):
                approval_status = gate.request_approval(
                    tool_name=tool_name,
                    risk_level=risk_level,
                    args=kwargs,
                    scope=permission_scope,
                    approval_id=approval_id
                )
                if approval_status != ApprovalStatus.APPROVED:
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] Authorization for tool '{tool_name}' ({risk_level}) was rejected by user."
                    logger.warning(denial_msg)
                    self.audit_logger.record_event(AuditEvent(
                        timestamp=start_time,
                        tool_name=tool_name,
                        risk_level=str(risk_level),
                        permission_scope=permission_scope,
                        args=kwargs,
                        policy_decision=policy_decision.value,
                        approval_status=approval_status.value,
                        execution_status=ExecutionStatus.DENIED.value,
                        execution_time_ms=execution_time_ms,
                        error_message="User approval rejected"
                    ))
                    return denial_msg

            else:
                # Stateful Approval System Flow
                if not approval_id:
                    # Step 3a: Create Approval Request & return pending notification
                    req = self.approval_manager.create_request(
                        tool_name=tool_name,
                        risk_level=risk_level,
                        args=kwargs,
                        scope=permission_scope,
                        required_permission=required_permission,
                        principal_id=principal_id,
                        session_id=session_id
                    )
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    pending_msg = (
                        f"[SECURITY APPROVAL REQUIRED] Tool '{tool_name}' ({risk_level}) requires human authorization. "
                        f"Approval ID: '{req.approval_id}'. Use '/api/approvals/{req.approval_id}/approve' or CLI 'approve {req.approval_id}'."
                    )
                    logger.info(f"Execution paused pending user approval for tool '{tool_name}' (Approval ID: {req.approval_id})")
                    self.audit_logger.record_event(AuditEvent(
                        timestamp=start_time,
                        tool_name=tool_name,
                        risk_level=str(risk_level),
                        permission_scope=permission_scope,
                        args=kwargs,
                        policy_decision=policy_decision.value,
                        approval_status=ApprovalStatus.PENDING.value,
                        execution_status=ExecutionStatus.DENIED.value,
                        execution_time_ms=execution_time_ms,
                        error_message="Execution paused pending approval"
                    ))
                    return pending_msg

                # Step 3b: Validate provided approval_id
                req = self.approval_manager.get_request(approval_id)
                if not req:
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] Invalid or unknown approval ID '{approval_id}'."
                    logger.warning(denial_msg)
                    return denial_msg

                # Check state
                if req.state != ApprovalState.APPROVED:
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] Approval request '{approval_id}' is in state '{req.state.value}' (must be APPROVED)."
                    logger.warning(denial_msg)
                    return denial_msg

                # Check replay / single-use flag
                if req.used:
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] Approval request '{approval_id}' has already been executed (replay blocked)."
                    logger.warning(denial_msg)
                    return denial_msg

                # Check expiration
                if req.is_expired:
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] Approval request '{approval_id}' has expired."
                    logger.warning(denial_msg)
                    return denial_msg

                # Check payload binding hash (verify tool_name, arguments, scope, permission, principal match)
                current_args_hash = compute_raw_args_hash(kwargs)
                current_binding = compute_binding_hash(
                    principal_id=principal_id,
                    tool_name=tool_name,
                    action="execute",
                    resource_scope=permission_scope,
                    permission=required_permission,
                    raw_args_hash=current_args_hash
                )
                if req.binding_hash != current_binding:
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] Approval request '{approval_id}' payload binding mismatch (arguments or scope mutated post-approval)."
                    logger.warning(denial_msg)
                    return denial_msg

                # MANDATORY REVALIDATION: Re-evaluate Permission Engine policy
                reval_decision = self.policy_engine.evaluate(
                    tool_name=tool_name,
                    risk_level=risk_level,
                    requires_approval=requires_approval,
                    scope=permission_scope,
                    kwargs=kwargs,
                    required_permission=required_permission
                )
                if reval_decision in (PolicyDecision.DENY, PolicyDecision.BLOCK):
                    execution_time_ms = (time.time() - start_time) * 1000.0
                    denial_msg = f"[SECURITY DENIAL] APPROVAL_EXECUTION_BLOCKED: Security policy revalidation denied execution (Policy decision: {reval_decision.value})."
                    logger.warning(denial_msg)
                    self.audit_logger.record_event(AuditEvent(
                        timestamp=start_time,
                        tool_name=tool_name,
                        risk_level=str(risk_level),
                        permission_scope=permission_scope,
                        args=kwargs,
                        policy_decision=reval_decision.value,
                        approval_status=ApprovalStatus.APPROVED.value,
                        execution_status=ExecutionStatus.DENIED.value,
                        execution_time_ms=execution_time_ms,
                        error_message="Policy revalidation failed post-approval"
                    ))
                    return denial_msg

                # Mark request as executed/used (replay prevention)
                self.approval_manager.mark_executed(approval_id)
                approval_status = ApprovalStatus.APPROVED

        # 4. Timeout-Guarded Execution
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(tool.execute, **kwargs)
                result = future.result(timeout=timeout_seconds)

            execution_time_ms = (time.time() - start_time) * 1000.0
            self.audit_logger.record_event(AuditEvent(
                timestamp=start_time,
                tool_name=tool_name,
                risk_level=str(risk_level),
                permission_scope=permission_scope,
                args=kwargs,
                policy_decision=policy_decision.value,
                approval_status=approval_status.value,
                execution_status=ExecutionStatus.SUCCESS.value,
                execution_time_ms=execution_time_ms
            ))
            return str(result)

        except concurrent.futures.TimeoutError:
            execution_time_ms = (time.time() - start_time) * 1000.0
            error_msg = f"Tool '{tool_name}' execution timed out after {timeout_seconds}s."
            logger.error(error_msg)

            cancellation_attempted = False
            if hasattr(tool, "cancel") and callable(getattr(tool, "cancel")):
                try:
                    tool.cancel()
                    cancellation_attempted = True
                    logger.info(f"Cancellation signal sent to timed-out tool '{tool_name}'.")
                except Exception as cancel_err:
                    logger.error(f"Failed to cancel timed-out tool '{tool_name}': {cancel_err}")
            
            self.audit_logger.record_event(AuditEvent(
                timestamp=start_time,
                tool_name=tool_name,
                risk_level=str(risk_level),
                permission_scope=permission_scope,
                args=kwargs,
                policy_decision=policy_decision.value,
                approval_status=approval_status.value,
                execution_status=ExecutionStatus.TIMED_OUT.value,
                execution_time_ms=execution_time_ms,
                error_message=error_msg
            ))
            status_suffix = " (Cancellation attempted)." if cancellation_attempted else "."
            return f"[SECURITY ERROR] Tool execution timed out after {timeout_seconds} seconds{status_suffix}"

        except Exception as exec_err:
            execution_time_ms = (time.time() - start_time) * 1000.0
            error_msg = str(exec_err)
            logger.error(f"Error executing tool '{tool_name}': {exec_err}")
            
            self.audit_logger.record_event(AuditEvent(
                timestamp=start_time,
                tool_name=tool_name,
                risk_level=str(risk_level),
                permission_scope=permission_scope,
                args=kwargs,
                policy_decision=policy_decision.value,
                approval_status=approval_status.value,
                execution_status=ExecutionStatus.FAILED.value,
                execution_time_ms=execution_time_ms,
                error_message=error_msg
            ))
            return f"Error executing tool '{tool_name}': {error_msg}"

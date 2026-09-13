import uuid
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from backend.security.enums import ApprovalStatus, RiskLevel, ApprovalState, ApprovalDecisionAction
from backend.security.approval_models import (
    ApprovalRequest,
    redact_sensitive_arguments,
    compute_raw_args_hash,
    compute_binding_hash
)
from backend.storage.approval_store import ApprovalStore
from backend.core.logging.logger import logger


class ApprovalGate(ABC):
    """Abstract interface for authorizing approval-required tool executions."""

    @abstractmethod
    def request_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        args: Dict[str, Any],
        scope: str,
        approval_id: Optional[str] = None
    ) -> ApprovalStatus:
        """
        Request user authorization to execute a tool.
        Returns ApprovalStatus.APPROVED, REJECTED, PENDING, or EXPIRED.
        """
        pass


class AutoApprovalGate(ApprovalGate):
    """
    Programmatic ApprovalGate for automated testing or legacy callers.
    Can be set to auto-approve, auto-reject, or execute a custom approval callback.
    """

    def __init__(self, default_approved: bool = False, callback: Optional[Any] = None):
        self.default_approved = default_approved
        self.callback = callback

    def request_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        args: Dict[str, Any],
        scope: str,
        approval_id: Optional[str] = None
    ) -> ApprovalStatus:
        if self.callback:
            try:
                approved = self.callback(tool_name, risk_level, args, scope)
                return ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            except Exception as e:
                logger.error(f"Approval callback raised exception: {e}")
                return ApprovalStatus.REJECTED

        if self.default_approved:
            logger.info(f"ApprovalGate: Auto-approving tool '{tool_name}' ({risk_level})")
            return ApprovalStatus.APPROVED
        else:
            logger.warning(f"ApprovalGate: Auto-rejecting tool '{tool_name}' ({risk_level})")
            return ApprovalStatus.REJECTED


class ApprovalManager:
    """
    Central Approval Manager for ERIS v2.9.1.
    Manages approval request lifecycles, SQLite persistence, state transitions,
    secret redaction, payload binding, deduplication, and expiration.
    """

    def __init__(self, store: Optional[ApprovalStore] = None, default_ttl_seconds: float = 300.0):
        self.store = store or ApprovalStore()
        self.default_ttl_seconds = default_ttl_seconds

    def create_request(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        args: Dict[str, Any],
        scope: str,
        required_permission: str = "tool.execute",
        principal_id: str = "user",
        session_id: Optional[str] = None,
        reason: Optional[str] = None,
        ttl_seconds: Optional[float] = None
    ) -> ApprovalRequest:
        """
        Creates a new ApprovalRequest in PENDING state or returns an existing identical active request.
        Arguments are redacted to protect secrets in storage/logs.
        """
        self.store.mark_expired()

        raw_args_hash = compute_raw_args_hash(args)
        binding_hash = compute_binding_hash(
            principal_id=principal_id,
            tool_name=tool_name,
            action="execute",
            resource_scope=scope,
            permission=required_permission,
            raw_args_hash=raw_args_hash
        )

        # Deduplication check: return active PENDING request if identical
        existing = self.store.find_active_pending(binding_hash=binding_hash, session_id=session_id)
        if existing and not existing.is_expired:
            logger.info(f"ApprovalManager: Reusing existing PENDING request '{existing.approval_id}' for tool '{tool_name}'.")
            return existing

        now = time.time()
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        expires_at = now + ttl

        redacted_args = redact_sensitive_arguments(args)
        approval_id = str(uuid.uuid4())
        request_id = str(uuid.uuid4())

        default_reason = f"Execution of tool '{tool_name}' ({risk_level}) requires explicit user authorization."

        req = ApprovalRequest(
            approval_id=approval_id,
            request_id=request_id,
            session_id=session_id,
            principal_id=principal_id,
            tool_name=tool_name,
            action="execute",
            arguments=redacted_args,
            raw_arguments_hash=raw_args_hash,
            resource_scope=scope,
            permission=required_permission,
            risk_level=risk_level,
            reason=reason or default_reason,
            created_at=now,
            expires_at=expires_at,
            state=ApprovalState.PENDING,
            binding_hash=binding_hash
        )

        self.store.store_request(req)
        logger.info(f"APPROVAL_CREATED: Created approval request '{approval_id}' for tool '{tool_name}' (Risk: {risk_level}, Scope: {scope}, Expires in {ttl:.0f}s)")
        return req

    def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieves an approval request and checks for auto-expiration."""
        req = self.store.get_request(approval_id)
        if not req:
            return None

        # Check and handle expiration
        if req.state == ApprovalState.PENDING and req.is_expired:
            self.store.update_state(approval_id=approval_id, new_state=ApprovalState.EXPIRED)
            req.state = ApprovalState.EXPIRED
            logger.info(f"APPROVAL_EXPIRED: Request '{approval_id}' expired at {req.expires_at}.")

        return req

    def list_pending(self, session_id: Optional[str] = None) -> List[ApprovalRequest]:
        """Lists active PENDING approval requests."""
        self.store.mark_expired()
        return self.store.list_pending(session_id=session_id)

    def list_all(self, limit: int = 100) -> List[ApprovalRequest]:
        """Lists all approval requests."""
        self.store.mark_expired()
        return self.store.list_all(limit=limit)

    def decide(
        self,
        approval_id: str,
        action: ApprovalDecisionAction,
        decided_by: str = "user"
    ) -> ApprovalRequest:
        """
        Applies a human decision (APPROVE, REJECT, CANCEL, EXPIRE) to a PENDING request.
        Strictly validates state transitions to prevent resurrection of terminal states.
        """
        req = self.get_request(approval_id)
        if not req:
            raise ValueError(f"Approval request '{approval_id}' not found.")

        if req.state != ApprovalState.PENDING:
            raise ValueError(
                f"Invalid approval state transition: Cannot perform action '{action.value}' on approval '{approval_id}' currently in terminal state '{req.state.value}'."
            )

        if req.is_expired:
            self.store.update_state(approval_id=approval_id, new_state=ApprovalState.EXPIRED, decided_by=decided_by)
            req.state = ApprovalState.EXPIRED
            logger.warning(f"APPROVAL_EXPIRED: Cannot perform action '{action.value}' on expired request '{approval_id}'.")
            raise ValueError(f"Approval request '{approval_id}' has expired.")

        now = time.time()
        target_state_map = {
            ApprovalDecisionAction.APPROVE: ApprovalState.APPROVED,
            ApprovalDecisionAction.REJECT: ApprovalState.REJECTED,
            ApprovalDecisionAction.CANCEL: ApprovalState.CANCELLED,
            ApprovalDecisionAction.EXPIRE: ApprovalState.EXPIRED
        }

        new_state = target_state_map[action]
        updated = self.store.update_state(
            approval_id=approval_id,
            new_state=new_state,
            decided_by=decided_by,
            decided_at=now
        )

        if not updated:
            raise RuntimeError(f"Failed to update state for approval request '{approval_id}'.")

        req.state = new_state
        req.decided_by = decided_by
        req.decided_at = now

        log_event_name = f"APPROVAL_{action.name}"
        logger.info(f"{log_event_name}: Request '{approval_id}' transitioned to state '{new_state.value}' by '{decided_by}'.")
        return req

    def approve(self, approval_id: str, decided_by: str = "user") -> ApprovalRequest:
        """Explicitly approve a pending request."""
        return self.decide(approval_id=approval_id, action=ApprovalDecisionAction.APPROVE, decided_by=decided_by)

    def reject(self, approval_id: str, decided_by: str = "user") -> ApprovalRequest:
        """Explicitly reject a pending request."""
        return self.decide(approval_id=approval_id, action=ApprovalDecisionAction.REJECT, decided_by=decided_by)

    def cancel(self, approval_id: str, decided_by: str = "user") -> ApprovalRequest:
        """Cancel a pending request."""
        return self.decide(approval_id=approval_id, action=ApprovalDecisionAction.CANCEL, decided_by=decided_by)

    def mark_executed(self, approval_id: str) -> bool:
        """Marks an approved request as EXECUTED and used (replay protection)."""
        return self.store.update_state(
            approval_id=approval_id,
            new_state=ApprovalState.EXECUTED,
            mark_used=True
        )


class SystemApprovalGate(ApprovalGate):
    """
    ApprovalGate implementation bridging CentralToolExecutor to ApprovalManager.
    """

    def __init__(self, manager: Optional[ApprovalManager] = None):
        self.manager = manager or ApprovalManager()

    def request_approval(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        args: Dict[str, Any],
        scope: str,
        approval_id: Optional[str] = None
    ) -> ApprovalStatus:
        if approval_id:
            req = self.manager.get_request(approval_id)
            if not req:
                return ApprovalStatus.REJECTED
            if req.state == ApprovalState.APPROVED and not req.used and not req.is_expired:
                return ApprovalStatus.APPROVED
            elif req.state == ApprovalState.REJECTED:
                return ApprovalStatus.REJECTED
            elif req.state == ApprovalState.EXPIRED or req.is_expired:
                return ApprovalStatus.EXPIRED
            elif req.state == ApprovalState.CANCELLED:
                return ApprovalStatus.CANCELLED
            return ApprovalStatus.PENDING
        
        # If no approval_id provided, create a pending request
        req = self.manager.create_request(
            tool_name=tool_name,
            risk_level=risk_level,
            args=args,
            scope=scope
        )
        return ApprovalStatus.PENDING

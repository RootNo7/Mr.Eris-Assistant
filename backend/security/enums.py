from enum import Enum, IntEnum

class RiskLevel(IntEnum):
    """
    Tool risk level classification hierarchy.
    T0: Read Only / Zero Risk (Informational)
    T1: Low Risk / Reversible (Read-Write)
    T2: Medium Risk / State Change (Reversible Write)
    T3: High Risk / Terminal / Destructive (Requires Confirmation)
    T4: Critical Risk / Unsafe System Operations (Always Denied / Restricted)
    """
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3
    T4 = 4

    def __str__(self) -> str:
        return f"T{self.value}"


class PolicyDecision(Enum):
    """Outcome of policy evaluation for a tool execution request."""
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK = "block"



class SecurityMode(Enum):
    """System-wide security posture mode."""
    PERMISSIVE = "permissive"
    BALANCED = "balanced"
    STRICT = "strict"


class ApprovalStatus(Enum):
    """Status of approval gate check."""
    APPROVED = "approved"
    REJECTED = "rejected"
    BYPASSED = "bypassed"
    NOT_REQUIRED = "not_required"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"
    EXECUTED = "executed"


class ApprovalState(Enum):
    """Lifecycle state machine for ERIS Approval Requests (v2.9.1)."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    EXECUTED = "executed"


class ApprovalDecisionAction(Enum):
    """Human decision actions for approval requests (v2.9.1)."""
    APPROVE = "approve"
    REJECT = "reject"
    CANCEL = "cancel"
    EXPIRE = "expire"



class ExecutionStatus(Enum):
    """Final status of tool execution."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    DENIED = "denied"
    VALIDATION_ERROR = "validation_error"

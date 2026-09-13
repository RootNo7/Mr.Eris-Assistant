import json
import hashlib
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional
from backend.security.enums import RiskLevel, ApprovalState, PolicyDecision


SENSITIVE_KEY_SUBSTRINGS = {
    "password", "passwd", "secret", "token", "key", "credential",
    "auth", "private", "api_key", "apikey", "bearer"
}


def redact_sensitive_arguments(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Returns a copy of the argument dictionary with sensitive values redacted.
    Protects passwords, API keys, bearer tokens, and credentials from log/storage leaks.
    """
    if not isinstance(args, dict):
        return args

    redacted = {}
    for k, v in args.items():
        k_lower = str(k).lower()
        if any(sub in k_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
            redacted[k] = "<redacted>"
        elif isinstance(v, dict):
            redacted[k] = redact_sensitive_arguments(v)
        elif isinstance(v, list):
            redacted[k] = [
                redact_sensitive_arguments(item) if isinstance(item, dict) else item
                for item in v
            ]
        else:
            redacted[k] = v
    return redacted


def compute_raw_args_hash(args: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 digest of tool arguments."""
    try:
        canonical_str = json.dumps(args, sort_keys=True, default=str)
    except Exception:
        canonical_str = str(sorted(args.items())) if isinstance(args, dict) else str(args)
    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()


def compute_binding_hash(
    principal_id: str,
    tool_name: str,
    action: str,
    resource_scope: str,
    permission: str,
    raw_args_hash: str
) -> str:
    """
    Computes a cryptographic binding hash linking the approval request to the exact action payload.
    Used for tamper protection and revalidation.
    """
    payload = f"{principal_id}|{tool_name}|{action}|{resource_scope}|{permission}|{raw_args_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class ApprovalRequest:
    """
    Strongly-typed Approval Request model for ERIS v2.9.1.
    Represents an explicit authorization ticket required for a REQUIRE_APPROVAL policy decision.
    """
    approval_id: str
    request_id: str
    principal_id: str
    tool_name: str
    action: str
    arguments: Dict[str, Any]  # Redacted representation safe for storage/UI
    raw_arguments_hash: str
    resource_scope: str
    permission: str
    risk_level: RiskLevel
    reason: str
    created_at: float
    expires_at: float
    state: ApprovalState = ApprovalState.PENDING
    session_id: Optional[str] = None
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    binding_hash: str = ""
    used: bool = False

    def __post_init__(self):
        if not self.binding_hash:
            self.binding_hash = compute_binding_hash(
                principal_id=self.principal_id,
                tool_name=self.tool_name,
                action=self.action,
                resource_scope=self.resource_scope,
                permission=self.permission,
                raw_args_hash=self.raw_arguments_hash
            )

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert approval request to serializable dictionary format."""
        res = {
            "approval_id": self.approval_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "principal_id": self.principal_id,
            "tool_name": self.tool_name,
            "action": self.action,
            "arguments": self.arguments,
            "raw_arguments_hash": self.raw_arguments_hash,
            "resource_scope": self.resource_scope,
            "permission": self.permission,
            "risk_level": int(self.risk_level),
            "reason": self.reason,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "state": self.state.value if isinstance(self.state, ApprovalState) else str(self.state),
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "binding_hash": self.binding_hash,
            "used": self.used,
            "is_expired": self.is_expired
        }
        return res

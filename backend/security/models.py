"""
backend/security/models.py

ERIS v2.9.0 Permission Data Models

Structured records for permission requests, decisions, and policy rules.
Provides end-to-end traceability from request through policy evaluation
to final decision, enabling future approval workflows (v2.9.1).
"""

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from uuid import uuid4
import fnmatch

from backend.security.enums import RiskLevel, PolicyDecision


@dataclass
class PermissionRequest:
    """
    Structured permission request with audit trail.
    
    Captures all context needed to evaluate whether an action is authorized.
    Each request has a unique ID for traceability through the decision process.
    """
    
    request_id: str = field(default_factory=lambda: str(uuid4()))
    tool_name: str = ""
    permission: str = ""  # PermissionIdentifier value (e.g., "tool.execute")
    risk_level: RiskLevel = RiskLevel.T1
    resource: Optional[str] = None  # path, url, process name, or other resource identifier
    scope: str = "general"  # permission scope (e.g., "filesystem.read", "system.control")
    kwargs: Dict[str, Any] = field(default_factory=dict)
    principal: str = "user"  # "user", "internal", "scheduled", "plugin", etc.
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "request_id": self.request_id,
            "tool_name": self.tool_name,
            "permission": self.permission,
            "risk_level": str(self.risk_level),
            "resource": self.resource,
            "scope": self.scope,
            "kwargs": self.kwargs,
            "principal": self.principal,
            "timestamp": self.timestamp,
        }


@dataclass
class PermissionDecision:
    """
    Structured permission decision with full traceability.
    
    Records the outcome of policy evaluation, which policy rule was matched,
    and the reasoning. Enables audit trails and supports future approval
    workflows that need to reference specific decisions.
    """
    
    decision_id: str = field(default_factory=lambda: str(uuid4()))
    request: PermissionRequest = field(default_factory=PermissionRequest)
    decision: PolicyDecision = PolicyDecision.DENY  # ALLOW, DENY, or REQUIRE_APPROVAL
    decision_detail: str = "denied_by_policy"  # specific reason (see PermissionDecisionDetail enum)
    reason: str = ""  # human-readable explanation
    policy_id: Optional[str] = None  # ID of matched policy rule (for audit trail)
    risk_level: RiskLevel = RiskLevel.T1
    timestamp: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "decision_id": self.decision_id,
            "request": self.request.to_dict(),
            "decision": self.decision.value,
            "decision_detail": self.decision_detail,
            "reason": self.reason,
            "policy_id": self.policy_id,
            "risk_level": str(self.risk_level),
            "timestamp": self.timestamp,
        }


@dataclass
class PolicyRule:
    """
    A single permission evaluation rule.
    
    Rules are matched in priority order (lower number = higher priority).
    When a rule matches a permission request, its effect (allow, deny, require_approval)
    determines the authorization outcome.
    
    Supports wildcard patterns for flexible policy configuration.
    """
    
    rule_id: str  # e.g., "policy_default_t0_allow", "filesystem_workspace_read"
    permission: str  # PermissionIdentifier value or glob pattern (e.g., "filesystem.*")
    effect: str  # "allow", "deny", or "require_approval"
    
    # Risk level constraints
    risk_level_max: Optional[RiskLevel] = None  # allow up to this level (inclusive)
    risk_level_min: Optional[RiskLevel] = None  # allow from this level (inclusive)
    
    # Resource and scope patterns (glob syntax)
    resource_pattern: Optional[str] = None  # glob: "/approved/*", "/workspace/**", etc.
    scope_pattern: Optional[str] = None  # glob: "general", "system.*", "filesystem.*"
    principal_pattern: Optional[str] = None  # glob: "user", "internal*", "scheduled"
    tool_pattern: Optional[str] = None  # glob: "*", "files.*", specific tool name
    
    requires_approval: bool = False  # if True, effect becomes "require_approval"
    enabled: bool = True  # can disable a rule without deleting it
    priority: int = 100  # sort order: lower = evaluated first
    
    def matches_request(self, req: PermissionRequest) -> bool:
        """
        Check if this rule applies to the given permission request.
        
        Returns True if all specified patterns match the corresponding
        request attributes. Unspecified patterns are treated as wildcards
        (always match).
        """
        if not self.enabled:
            return False
        
        # Check permission match
        if not self._match_pattern(self.permission, req.permission):
            return False
        
        # Check tool name match
        if not self._match_pattern(self.tool_pattern, req.tool_name):
            return False
        
        # Check resource match
        if not self._match_pattern(self.resource_pattern, req.resource or ""):
            return False
        
        # Check scope match
        if not self._match_pattern(self.scope_pattern, req.scope):
            return False
        
        # Check principal match
        if not self._match_pattern(self.principal_pattern, req.principal):
            return False
        
        # Check risk level constraints
        if self.risk_level_max is not None:
            if req.risk_level > self.risk_level_max:
                return False
        
        if self.risk_level_min is not None:
            if req.risk_level < self.risk_level_min:
                return False
        
        return True
    
    @staticmethod
    def _match_pattern(pattern: Optional[str], value: str) -> bool:
        """
        Match value against pattern using fnmatch (glob syntax).
        
        If pattern is None or empty, considered a wildcard (always matches).
        Supports * (any characters) and ? (single character) wildcards.
        """
        if not pattern:
            return True
        
        return fnmatch.fnmatch(value, pattern)
    
    def validate(self) -> None:
        """
        Validate that this rule is well-formed.
        
        Raises ValueError if configuration is invalid.
        """
        if not self.rule_id:
            raise ValueError("rule_id is required")
        
        if self.effect not in ("allow", "deny", "require_approval"):
            raise ValueError(f"Invalid effect '{self.effect}': must be 'allow', 'deny', or 'require_approval'")
        
        if not self.permission:
            raise ValueError("permission is required")
        
        if self.priority < 0:
            raise ValueError("priority must be >= 0")


class PermissionDecisionDetail:
    """
    String constants for specific permission decision reasons.
    Used in PermissionDecision.decision_detail field for structured audit trails.
    """
    
    ALLOWED_BY_POLICY = "allowed_by_policy"
    DENIED_BY_POLICY = "denied_by_policy"
    DENIED_RISK_TOO_HIGH = "denied_risk_too_high"
    DENIED_T4_PROHIBITED = "denied_t4_prohibited"
    DENIED_UNKNOWN_PERMISSION = "denied_unknown_permission"
    DENIED_UNKNOWN_TOOL = "denied_unknown_tool"
    DENIED_FORBIDDEN_SCOPE = "denied_forbidden_scope"
    REQUIRES_APPROVAL_RISK = "requires_approval_risk"
    REQUIRES_APPROVAL_FLAG = "requires_approval_flag"

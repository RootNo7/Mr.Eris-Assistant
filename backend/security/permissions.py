import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, Optional, Set, List
from backend.security.enums import RiskLevel, PolicyDecision


class Permission(str, Enum):
    """Standard ERIS Permission Identifiers."""
    TOOL_READ = "tool.read"
    TOOL_EXECUTE = "tool.execute"
    FILESYSTEM_READ = "filesystem.read"
    FILESYSTEM_WRITE = "filesystem.write"
    NETWORK_ACCESS = "network.access"
    PROCESS_MANAGE = "process.manage"
    SYSTEM_CONTROL = "system.control"
    SYSTEM_ADMIN = "system.admin"

    def __str__(self) -> str:
        return self.value


@dataclass
class Principal:
    """Represents an authenticated principal requesting tool execution."""
    id: str = "user"
    type: str = "user"  # user, eris_internal, scheduled_task, subagent, plugin
    granted_permissions: Set[str] = field(default_factory=set)
    is_admin: bool = False


@dataclass
class ResourceScope:
    """Represents scope constraints for a target resource."""
    allowed_scopes: List[str] = field(default_factory=list)
    forbidden_scopes: List[str] = field(default_factory=list)

    def is_allowed(self, resource: str) -> bool:
        """Determines whether a resource target is allowed under current scope limits."""
        if not resource or resource == "*":
            return True
            
        # Check explicit forbidden scopes
        for forbidden in self.forbidden_scopes:
            if forbidden and (forbidden == resource or resource.startswith(forbidden)):
                return False

        # If allowed scopes specified, must match at least one
        if self.allowed_scopes:
            return any(allowed == resource or resource.startswith(allowed) or allowed == "*" for allowed in self.allowed_scopes)

        return True


@dataclass
class PermissionRequest:
    """Encapsulates a tool execution authorization request."""
    tool_name: str
    action: str = "execute"
    arguments: Dict[str, Any] = field(default_factory=dict)
    resource: str = "*"
    required_permission: str = "tool.execute"
    risk_level: RiskLevel = RiskLevel.T1


@dataclass
class PermissionContext:
    """Contextual metadata surrounding a permission authorization request."""
    principal: Principal = field(default_factory=Principal)
    session_id: Optional[str] = None
    environment: str = "development"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PermissionDecision:
    """Structured decision output from Permission Engine authorization evaluation."""
    decision: PolicyDecision
    reason: str
    policy_id: str
    risk_level: RiskLevel
    required_permission: str
    tool_name: str
    resource: str
    timestamp: float = field(default_factory=time.time)
    principal_id: str = "user"

    def is_allowed(self) -> bool:
        return self.decision == PolicyDecision.ALLOW

    def is_denied(self) -> bool:
        return self.decision in (PolicyDecision.DENY, PolicyDecision.BLOCK)

    def requires_approval(self) -> bool:
        return self.decision == PolicyDecision.REQUIRE_APPROVAL

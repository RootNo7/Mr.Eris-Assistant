from typing import Dict, Any, Optional, Set
from backend.security.enums import RiskLevel, PolicyDecision, SecurityMode
from backend.security.permissions import (
    PermissionRequest,
    PermissionContext,
    PermissionDecision,
    Principal
)
from backend.security.engine import PermissionEngine
from backend.core.logging.logger import logger
from backend.core.config.settings import Config


class PolicyEngine:
    """
    Adapter layer delegating policy evaluation to Central PermissionEngine.
    Maintains backward compatibility with legacy callers while enforcing 
    v2.9.0 PermissionEngine decision model and security boundary.
    """

    def __init__(
        self,
        mode: Optional[SecurityMode] = None,
        max_auto_risk: Optional[RiskLevel] = None,
        forbidden_scopes: Optional[Set[str]] = None,
        config: Optional[Config] = None
    ):
        self.permission_engine = PermissionEngine(
            mode=mode,
            max_auto_risk=max_auto_risk,
            forbidden_scopes=forbidden_scopes,
            config=config
        )

    @property
    def mode(self) -> SecurityMode:
        return self.permission_engine.mode

    @mode.setter
    def mode(self, value: SecurityMode) -> None:
        self.permission_engine.mode = value

    @property
    def max_auto_risk(self) -> RiskLevel:
        return self.permission_engine.max_auto_risk

    @max_auto_risk.setter
    def max_auto_risk(self, value: RiskLevel) -> None:
        self.permission_engine.max_auto_risk = value

    @property
    def forbidden_scopes(self) -> Set[str]:
        return self.permission_engine.forbidden_scopes

    @forbidden_scopes.setter
    def forbidden_scopes(self, value: Set[str]) -> None:
        self.permission_engine.forbidden_scopes = value

    def evaluate(
        self,
        tool_name: str,
        risk_level: RiskLevel,
        requires_approval: bool,
        scope: str,
        kwargs: Dict[str, Any],
        required_permission: str = "tool.execute",
        context: Optional[PermissionContext] = None
    ) -> PolicyDecision:
        """
        Evaluates a tool execution request through PermissionEngine.
        Returns PolicyDecision (ALLOW, DENY, REQUIRE_APPROVAL, or BLOCK).
        """
        resource = scope
        # Determine resource if passed in kwargs (e.g. file_path, directory_path, command, url)
        if kwargs:
            for res_key in ("file_path", "directory_path", "source_path", "path", "command", "url", "app_name"):
                if res_key in kwargs and kwargs[res_key]:
                    resource = str(kwargs[res_key])
                    break

        request = PermissionRequest(
            tool_name=tool_name,
            action="execute",
            arguments=kwargs,
            resource=resource,
            required_permission=required_permission,
            risk_level=risk_level
        )

        # If tool explicitly has requires_approval flag set, force risk/approval check
        if requires_approval and request.risk_level < RiskLevel.T3:
            request.risk_level = RiskLevel.T3

        decision = self.permission_engine.evaluate(request=request, context=context)
        return decision.decision

    def evaluate_request(
        self,
        request: PermissionRequest,
        context: Optional[PermissionContext] = None
    ) -> PermissionDecision:
        """Evaluates a structured PermissionRequest and returns a full PermissionDecision object."""
        return self.permission_engine.evaluate(request=request, context=context)

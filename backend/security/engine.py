import time
from typing import Dict, Any, Optional, Set, List
from backend.security.enums import RiskLevel, PolicyDecision, SecurityMode
from backend.security.permissions import (
    Permission,
    Principal,
    ResourceScope,
    PermissionRequest,
    PermissionContext,
    PermissionDecision
)
from backend.core.logging.logger import logger
from backend.core.config.settings import Config


class PermissionEngine:
    """
    Central ERIS Permission Engine.
    Enforces deterministic authorization decision logic across all tools and entry points.
    Implements strict default-deny and fail-closed evaluation.
    """

    def __init__(
        self,
        mode: Optional[SecurityMode] = None,
        max_auto_risk: Optional[RiskLevel] = None,
        forbidden_scopes: Optional[Set[str]] = None,
        forbidden_tools: Optional[Set[str]] = None,
        allowed_tools: Optional[Set[str]] = None,
        config: Optional[Config] = None
    ):
        self._valid_config = True
        try:
            self.config = config or Config()
            
            # Security posture mode
            if mode is not None:
                if isinstance(mode, SecurityMode):
                    self.mode = mode
                else:
                    mode_str = str(mode).lower()
                    if mode_str == "strict":
                        self.mode = SecurityMode.STRICT
                    elif mode_str == "permissive":
                        self.mode = SecurityMode.PERMISSIVE
                    elif mode_str == "balanced":
                        self.mode = SecurityMode.BALANCED
                    else:
                        logger.error(f"PermissionEngine: Invalid ERIS_SECURITY_MODE '{mode_str}', failing closed.")
                        self._valid_config = False
                        self.mode = SecurityMode.STRICT
            else:
                mode_str = str(getattr(self.config, "ERIS_SECURITY_MODE", "balanced")).lower()
                if mode_str == "strict":
                    self.mode = SecurityMode.STRICT
                elif mode_str == "permissive":
                    self.mode = SecurityMode.PERMISSIVE
                elif mode_str == "balanced":
                    self.mode = SecurityMode.BALANCED
                else:
                    logger.error(f"PermissionEngine: Invalid ERIS_SECURITY_MODE '{mode_str}', failing closed.")
                    self._valid_config = False
                    self.mode = SecurityMode.STRICT

            # Max auto-approved risk level
            if max_auto_risk is not None:
                if isinstance(max_auto_risk, RiskLevel):
                    self.max_auto_risk = max_auto_risk
                else:
                    risk_str = str(max_auto_risk).upper()
                    if risk_str == "T0":
                        self.max_auto_risk = RiskLevel.T0
                    elif risk_str == "T1":
                        self.max_auto_risk = RiskLevel.T1
                    elif risk_str == "T2":
                        self.max_auto_risk = RiskLevel.T2
                    else:
                        logger.error(f"PermissionEngine: Invalid ERIS_MAX_AUTO_RISK '{risk_str}', failing closed.")
                        self._valid_config = False
                        self.max_auto_risk = RiskLevel.T0
            else:
                risk_str = str(getattr(self.config, "ERIS_MAX_AUTO_RISK", "T1")).upper()
                if risk_str == "T0":
                    self.max_auto_risk = RiskLevel.T0
                elif risk_str == "T1":
                    self.max_auto_risk = RiskLevel.T1
                elif risk_str == "T2":
                    self.max_auto_risk = RiskLevel.T2
                else:
                    logger.error(f"PermissionEngine: Invalid ERIS_MAX_AUTO_RISK '{risk_str}', failing closed.")
                    self._valid_config = False
                    self.max_auto_risk = RiskLevel.T0

            self.forbidden_scopes: Set[str] = set(forbidden_scopes or [])
            self.forbidden_tools: Set[str] = set(forbidden_tools or [])
            self.allowed_tools: Optional[Set[str]] = set(allowed_tools) if allowed_tools is not None else None

        except Exception as err:
            logger.error(f"PermissionEngine initialization error: {err}")
            self._valid_config = False
            self.mode = SecurityMode.STRICT
            self.max_auto_risk = RiskLevel.T0
            self.forbidden_scopes = set()
            self.forbidden_tools = set()
            self.allowed_tools = set()

    def evaluate(
        self,
        request: PermissionRequest,
        context: Optional[PermissionContext] = None
    ) -> PermissionDecision:
        """
        Evaluates a tool permission request against context and security posture.
        Follows a strict 8-stage evaluation precedence order.
        Fails closed (DENY) on error or invalid policy configuration.
        """
        ctx = context or PermissionContext()
        timestamp = time.time()

        # Fail-closed check
        if not self._valid_config:
            logger.error(f"PermissionEngine: Policy config is invalid. Denying request for '{request.tool_name}'.")
            return PermissionDecision(
                decision=PolicyDecision.DENY,
                reason="Permission Engine configuration is invalid. Failing closed.",
                policy_id="FAIL_CLOSED_CONFIG_ERROR",
                risk_level=request.risk_level,
                required_permission=request.required_permission,
                tool_name=request.tool_name,
                resource=request.resource,
                timestamp=timestamp,
                principal_id=ctx.principal.id
            )

        try:
            # 1. Global Hard Block / T4 Prohibited Check
            if request.risk_level >= RiskLevel.T4:
                logger.warning(f"PermissionEngine: Hard block on tool '{request.tool_name}' — T4 critical risk operation.")
                return PermissionDecision(
                    decision=PolicyDecision.BLOCK,
                    reason=f"Execution of tool '{request.tool_name}' ({request.risk_level}) is prohibited by critical T4 security block.",
                    policy_id="STAGE_1_GLOBAL_HARD_BLOCK_T4",
                    risk_level=request.risk_level,
                    required_permission=request.required_permission,
                    tool_name=request.tool_name,
                    resource=request.resource,
                    timestamp=timestamp,
                    principal_id=ctx.principal.id
                )

            # 2. Principal Restriction Check
            principal = ctx.principal
            if principal.granted_permissions and not principal.is_admin:
                if request.required_permission not in principal.granted_permissions and "*" not in principal.granted_permissions:
                    logger.warning(f"PermissionEngine: Principal '{principal.id}' lacks permission '{request.required_permission}'.")
                    return PermissionDecision(
                        decision=PolicyDecision.DENY,
                        reason=f"Principal '{principal.id}' lacks required permission '{request.required_permission}'.",
                        policy_id="STAGE_2_PRINCIPAL_RESTRICTION",
                        risk_level=request.risk_level,
                        required_permission=request.required_permission,
                        tool_name=request.tool_name,
                        resource=request.resource,
                        timestamp=timestamp,
                        principal_id=principal.id
                    )

            # 3. Tool Restriction Check
            if request.tool_name in self.forbidden_tools:
                logger.warning(f"PermissionEngine: Tool '{request.tool_name}' is explicitly forbidden.")
                return PermissionDecision(
                    decision=PolicyDecision.DENY,
                    reason=f"Tool '{request.tool_name}' is explicitly forbidden by security policy.",
                    policy_id="STAGE_3_TOOL_RESTRICTION",
                    risk_level=request.risk_level,
                    required_permission=request.required_permission,
                    tool_name=request.tool_name,
                    resource=request.resource,
                    timestamp=timestamp,
                    principal_id=principal.id
                )

            if self.allowed_tools is not None and request.tool_name not in self.allowed_tools:
                logger.warning(f"PermissionEngine: Tool '{request.tool_name}' is not in allowed tools set.")
                return PermissionDecision(
                    decision=PolicyDecision.DENY,
                    reason=f"Tool '{request.tool_name}' is not in authorized tools list.",
                    policy_id="STAGE_3_TOOL_NOT_IN_ALLOWED_LIST",
                    risk_level=request.risk_level,
                    required_permission=request.required_permission,
                    tool_name=request.tool_name,
                    resource=request.resource,
                    timestamp=timestamp,
                    principal_id=principal.id
                )

            # 4. Resource Scope Restriction Check
            if request.resource in self.forbidden_scopes:
                logger.warning(f"PermissionEngine: Denying '{request.tool_name}' — resource '{request.resource}' is forbidden.")
                return PermissionDecision(
                    decision=PolicyDecision.DENY,
                    reason=f"Resource '{request.resource}' is explicitly forbidden by security scope.",
                    policy_id="STAGE_4_RESOURCE_SCOPE_RESTRICTION",
                    risk_level=request.risk_level,
                    required_permission=request.required_permission,
                    tool_name=request.tool_name,
                    resource=request.resource,
                    timestamp=timestamp,
                    principal_id=principal.id
                )

            # Check substring/prefix scope prohibitions
            for forbidden_scope in self.forbidden_scopes:
                if forbidden_scope and (forbidden_scope == request.resource or request.resource.startswith(forbidden_scope)):
                    logger.warning(f"PermissionEngine: Resource '{request.resource}' matched forbidden scope '{forbidden_scope}'.")
                    return PermissionDecision(
                        decision=PolicyDecision.DENY,
                        reason=f"Resource scope '{forbidden_scope}' is forbidden by security posture.",
                        policy_id="STAGE_4_RESOURCE_SCOPE_MATCH",
                        risk_level=request.risk_level,
                        required_permission=request.required_permission,
                        tool_name=request.tool_name,
                        resource=request.resource,
                        timestamp=timestamp,
                        principal_id=principal.id
                    )

            # 5. Risk Restriction Check (Posture Enforcement)
            if self.mode == SecurityMode.STRICT:
                if request.risk_level >= RiskLevel.T3:
                    return PermissionDecision(
                        decision=PolicyDecision.DENY,
                        reason=f"High risk tool '{request.tool_name}' ({request.risk_level}) is denied under STRICT security posture.",
                        policy_id="STAGE_5_RISK_STRICT_DENY",
                        risk_level=request.risk_level,
                        required_permission=request.required_permission,
                        tool_name=request.tool_name,
                        resource=request.resource,
                        timestamp=timestamp,
                        principal_id=principal.id
                    )
                elif request.risk_level > RiskLevel.T1:
                    return PermissionDecision(
                        decision=PolicyDecision.REQUIRE_APPROVAL,
                        reason=f"Medium risk tool '{request.tool_name}' ({request.risk_level}) requires user approval under STRICT posture.",
                        policy_id="STAGE_5_RISK_STRICT_APPROVAL",
                        risk_level=request.risk_level,
                        required_permission=request.required_permission,
                        tool_name=request.tool_name,
                        resource=request.resource,
                        timestamp=timestamp,
                        principal_id=principal.id
                    )

            # 6. Explicit Approval Requirement Check
            if request.risk_level > self.max_auto_risk or request.risk_level >= RiskLevel.T3:
                return PermissionDecision(
                    decision=PolicyDecision.REQUIRE_APPROVAL,
                    reason=f"Tool '{request.tool_name}' ({request.risk_level}) exceeds auto-approval threshold ({self.max_auto_risk}) and requires approval.",
                    policy_id="STAGE_6_APPROVAL_THRESHOLD_EXCEEDED",
                    risk_level=request.risk_level,
                    required_permission=request.required_permission,
                    tool_name=request.tool_name,
                    resource=request.resource,
                    timestamp=timestamp,
                    principal_id=principal.id
                )

            # 7. Explicit Allow Rule Check (Safe T0/T1 within bounds)
            if request.risk_level <= self.max_auto_risk and request.risk_level < RiskLevel.T3:
                return PermissionDecision(
                    decision=PolicyDecision.ALLOW,
                    reason=f"Tool '{request.tool_name}' ({request.risk_level}) authorized automatically under {self.mode.value.upper()} posture.",
                    policy_id="STAGE_7_EXPLICIT_ALLOW",
                    risk_level=request.risk_level,
                    required_permission=request.required_permission,
                    tool_name=request.tool_name,
                    resource=request.resource,
                    timestamp=timestamp,
                    principal_id=principal.id
                )

            # 8. Default Deny Fallback
            logger.warning(f"PermissionEngine: Default-deny fallback reached for tool '{request.tool_name}'.")
            return PermissionDecision(
                decision=PolicyDecision.DENY,
                reason=f"Access denied by default-deny security policy for tool '{request.tool_name}'.",
                policy_id="STAGE_8_DEFAULT_DENY",
                risk_level=request.risk_level,
                required_permission=request.required_permission,
                tool_name=request.tool_name,
                resource=request.resource,
                timestamp=timestamp,
                principal_id=principal.id
            )

        except Exception as eval_err:
            logger.error(f"PermissionEngine exception during evaluation: {eval_err}", exc_info=True)
            return PermissionDecision(
                decision=PolicyDecision.DENY,
                reason=f"Permission engine evaluation error for tool '{request.tool_name}': {eval_err}",
                policy_id="EXCEPTION_FAIL_CLOSED",
                risk_level=request.risk_level,
                required_permission=request.required_permission,
                tool_name=request.tool_name,
                resource=request.resource,
                timestamp=timestamp,
                principal_id=ctx.principal.id
            )

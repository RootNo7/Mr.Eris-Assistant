import os
import json
import time
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional
from backend.security.enums import RiskLevel, PolicyDecision, ApprovalStatus, ExecutionStatus
from backend.core.logging.logger import logger

SENSITIVE_PARAM_KEYS = {"api_key", "secret", "password", "token", "auth", "credential", "private_key"}


@dataclass
class AuditEvent:
    """Structured audit log record for every tool execution attempt."""
    timestamp: float
    tool_name: str
    risk_level: str
    permission_scope: str
    args: Dict[str, Any]
    policy_decision: str
    approval_status: str
    execution_status: str
    execution_time_ms: float
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Sanitize sensitive arguments
        sanitized_args = {}
        for k, v in self.args.items():
            if any(s_key in k.lower() for s_key in SENSITIVE_PARAM_KEYS):
                sanitized_args[k] = "***REDACTED***"
            else:
                sanitized_args[k] = v
        data["args"] = sanitized_args
        return data


class AuditLogger:
    """
    Manages append-only JSON Lines structured audit logging for ERIS tool executions.
    """

    def __init__(self, log_dir: Optional[str] = None):
        if not log_dir:
            log_dir = os.path.join(os.getcwd(), "backend", "storage", "audit")
        os.makedirs(log_dir, exist_ok=True)
        self.log_file = os.path.join(log_dir, "audit.log")

    def record_event(self, event: AuditEvent) -> None:
        """Appends an AuditEvent record to the local audit log file and logs to system logger."""
        event_dict = event.to_dict()
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event_dict) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit event to file: {e}")

        logger_msg = (
            f"[AUDIT] tool='{event.tool_name}' risk={event.risk_level} "
            f"decision={event.policy_decision} approval={event.approval_status} "
            f"status={event.execution_status} time={event.execution_time_ms:.1f}ms"
        )
        if event.execution_status == ExecutionStatus.SUCCESS.value:
            logger.info(logger_msg)
        else:
            logger.warning(f"{logger_msg} err='{event.error_message}'")

from abc import ABC, abstractmethod
from typing import Any, Callable, Optional
from backend.security.enums import RiskLevel


class BaseTool(ABC):
    """
    Abstract base class for all ERIS executable tools.
    Enforces required metadata for the Action Permission Framework.
    """
    name: str
    description: str
    risk_level: RiskLevel = RiskLevel.T1
    requires_approval: bool = False
    timeout_seconds: float = 10.0
    permission_scope: str = "general"
    required_permission: str = "tool.execute"
    enabled: bool = True
    side_effect_level: str = "none"  # none, low, medium, high, critical
    openai_name: Optional[str] = None  # Optional: override for OpenAI-compatible providers


    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Execute the tool logic and return a serializable result."""
        pass

    @abstractmethod
    def get_schema(self) -> Callable:
        """Returns the Python function/callable signature for AI Provider registration."""
        pass

    def cancel(self) -> None:
        """Optional hook to terminate processes or abort ongoing tool operations on timeout."""
        pass
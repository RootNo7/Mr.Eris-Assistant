"""
ERIS Base Exception Hierarchy.
Provides structured, domain-specific error types across backend subsystems.
"""

from typing import Any, Dict, Optional


class ERISError(Exception):
    """Base exception class for all ERIS system errors."""

    def __init__(
        self, 
        message: str, 
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} | Details: {self.details}"
        return self.message


class ConfigurationError(ERISError):
    """Raised when system configuration loading or validation fails."""
    pass


class ProviderError(ERISError):
    """Base exception for all AI Provider operation failures."""
    pass


class ProviderInitializationError(ProviderError):
    """Raised when an AI provider fails during initial authentication or setup."""
    pass


class ProviderAPIError(ProviderError):
    """Raised when runtime LLM generation or streaming requests fail."""
    pass
    
import pytest
from backend.core.exceptions import (
    ERISError,
    ConfigurationError,
    ProviderError,
    ProviderInitializationError,
    InvalidPromptError,
    ProviderAPIError,
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    MemoryError,
    MemoryStorageError,
    AuthenticationError
)

def test_exception_hierarchy():
    """Verify ERIS custom exceptions inherit from ERISError and appropriate Python built-in types."""
    assert issubclass(ConfigurationError, ERISError)
    assert issubclass(ConfigurationError, ValueError)

    assert issubclass(ProviderError, ERISError)
    assert issubclass(ProviderInitializationError, ProviderError)
    assert issubclass(ProviderInitializationError, RuntimeError)
    assert issubclass(InvalidPromptError, ProviderError)
    assert issubclass(InvalidPromptError, ValueError)
    assert issubclass(ProviderAPIError, ProviderError)

    assert issubclass(ToolError, ERISError)
    assert issubclass(ToolNotFoundError, ToolError)
    assert issubclass(ToolNotFoundError, KeyError)
    assert issubclass(ToolExecutionError, ToolError)

    assert issubclass(MemoryError, ERISError)
    assert issubclass(MemoryStorageError, MemoryError)

    assert issubclass(AuthenticationError, ERISError)
    assert issubclass(AuthenticationError, PermissionError)

def test_configuration_error_raise():
    """Verify ConfigurationError can be caught both as ERISError and ValueError."""
    with pytest.raises(ValueError):
        raise ConfigurationError("Missing configuration secret.")

    with pytest.raises(ERISError):
        raise ConfigurationError("Missing configuration secret.")

def test_invalid_prompt_error_raise():
    """Verify InvalidPromptError can be caught as ValueError and ProviderError."""
    with pytest.raises(ValueError):
        raise InvalidPromptError("Prompt is empty.")

    with pytest.raises(ProviderError):
        raise InvalidPromptError("Prompt is empty.")

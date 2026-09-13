"""
Structured exception hierarchy for ERIS (Evolutionary Responsive Intelligence System).

Custom exception classes inherit from both ERISError and corresponding Python
built-in exceptions (e.g. ValueError, RuntimeError, KeyError) to maintain full
backward compatibility with existing call sites and test assertions.
"""

class ERISError(Exception):
    """Base exception class for all ERIS system errors."""
    pass


# --- Configuration Exceptions ---

class ConfigurationError(ERISError, ValueError):
    """Raised when environment or system configuration validation fails."""
    pass


# --- AI Provider Exceptions ---

class ProviderError(ERISError):
    """Base exception for AI provider operational errors."""
    pass


class ProviderInitializationError(ProviderError, RuntimeError):
    """Raised when an AI provider fails to initialize."""
    pass


class InvalidPromptError(ProviderError, ValueError):
    """Raised when an invalid or empty prompt is provided to an AI provider."""
    pass


class ProviderAPIError(ProviderError):
    """Raised when an external AI provider API returns an unexpected error."""
    pass


# --- Tool Execution Exceptions ---

class ToolError(ERISError):
    """Base exception for tool execution failures."""
    pass


class ToolNotFoundError(ToolError, KeyError):
    """Raised when a requested tool is not registered in ToolRegistry."""
    pass


class ToolExecutionError(ToolError, RuntimeError):
    """Raised when a tool encounters an error during execution."""
    pass


# --- Memory Storage Exceptions ---

class MemoryError(ERISError):
    """Base exception for session or long-term memory operations."""
    pass


class MemoryStorageError(MemoryError, RuntimeError):
    """Raised when persistent memory read/write operations fail."""
    pass


# --- Security & Auth Exceptions ---

class AuthenticationError(ERISError, PermissionError):
    """Raised when API key verification fails."""
    pass


# --- Path & Filesystem Security Exceptions ---

class PathSecurityError(ERISError, PermissionError):
    """Base exception for filesystem security violations."""
    pass


class PathTraversalError(PathSecurityError):
    """Raised when a path traversal escape attempt (e.g. ../) is detected."""
    pass


class UnauthorizedPathError(PathSecurityError):
    """Raised when a path falls outside allowed filesystem roots."""
    pass


class FileTooLargeError(ERISError, ValueError):
    """Raised when a file exceeds maximum allowed read/write byte limit."""
    pass


# --- Orchestration Exceptions ---

class OrchestrationError(ERISError):
    """Base exception for orchestration loop failures."""
    pass


class OrchestrationTimeoutError(OrchestrationError, TimeoutError):
    """Raised when an orchestration task exceeds its maximum wall-clock time limit."""
    pass


class OrchestrationLoopBreakerError(OrchestrationError, RuntimeError):
    """Raised when an orchestration task exceeds max_steps or max_tool_calls."""
    pass


class OrchestrationCancelledError(OrchestrationError):
    """Raised when an orchestration task is cooperatively cancelled by the caller."""
    pass


# --- Voice Subsystem Exceptions ---

class VoiceError(ERISError):
    """Base exception for voice interface and audio pipeline failures."""
    pass


class AudioHardwareError(VoiceError, RuntimeError):
    """Raised when microphone or audio output device is unavailable or fails."""
    pass


class WakeWordError(VoiceError, RuntimeError):
    """Raised when wake-word detection engine encounters a runtime failure."""
    pass


class STTError(VoiceError, RuntimeError):
    """Raised when speech-to-text transcription engine fails."""
    pass


class TTSError(VoiceError, RuntimeError):
    """Raised when text-to-speech synthesis engine fails."""
    pass


class VoiceTimeoutError(VoiceError, TimeoutError):
    """Raised when a voice subsystem operation (STT, LLM, TTS, device) times out."""
    pass


class VoiceDeviceError(AudioHardwareError):
    """Raised when an audio hardware device fails, disconnects, or is occupied."""
    pass


class VoiceStaleResultError(VoiceError):
    """Raised when an asynchronous voice result belongs to a superseded turn or token."""
    pass


class VoiceHealthError(VoiceError):
    """Raised when voice subsystem health state transitions to FAILED or UNRECOVERABLE."""
    pass



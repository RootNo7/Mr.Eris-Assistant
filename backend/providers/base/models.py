"""
ERIS AI Provider Data Models.
Defines unified data structures for LLM request/response payloads.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    """Standardized message author roles."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(BaseModel):
    """Represents a single message in a conversation context."""
    role: MessageRole = Field(..., description="Author role of the message")
    content: str = Field(..., description="Text content of the message")
    metadata: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Optional provider-specific or system metadata"
    )


class LLMRequest(BaseModel):
    """Standard payload sent to an AI Provider for generation."""
    messages: List[ChatMessage] = Field(..., description="Ordered conversation history")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling randomness")
    max_tokens: Optional[int] = Field(default=None, gt=0, description="Token generation limit")
    top_p: Optional[float] = Field(default=0.95, ge=0.0, le=1.0, description="Nucleus sampling cutoff")
    stop_sequences: Optional[List[str]] = Field(default=None, description="Sequence triggers to cease generation")


class LLMResponse(BaseModel):
    """Unified response object returned by an AI Provider."""
    content: str = Field(..., description="Generated text response from model")
    model_name: str = Field(..., description="Model identifier used for inference")
    prompt_tokens: int = Field(default=0, ge=0, description="Input tokens processed")
    completion_tokens: int = Field(default=0, ge=0, description="Output tokens generated")
    finish_reason: Optional[str] = Field(default=None, description="Reason for stopping generation")
    raw_response: Optional[Dict[str, Any]] = Field(default=None, description="Unmodified underlying API response")


class StreamChunk(BaseModel):
    """Individual data fragment emitted during real-time response streaming."""
    delta: str = Field(..., description="Incremental text fragment")
    finish_reason: Optional[str] = Field(default=None, description="Set on final stream frame")


class ProviderCapabilities(BaseModel):
    """Metadata describing features supported by a provider implementation."""
    provider_name: str = Field(..., description="Unique provider key (e.g. 'gemini')")
    supports_streaming: bool = Field(default=True, description="Real-time token streaming capability")
    supports_tools: bool = Field(default=False, description="Function calling capability")
    supports_vision: bool = Field(default=False, description="Multimodal image processing")
    supported_models: List[str] = Field(default_factory=list, description="Available supported model strings")
    
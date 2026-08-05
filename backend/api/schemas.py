"""
ERIS FastAPI Endpoint Schemas.
Defines Pydantic models for REST and SSE API requests and responses.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Payload to create a new chat session."""
    title: str = Field(default="New Session", description="Display title for the session")
    system_prompt: Optional[str] = Field(
        default=None, 
        description="Custom system instruction for the session context"
    )


class SessionResponse(BaseModel):
    """Response representing session status and metadata."""
    session_id: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class SendMessageRequest(BaseModel):
    """Payload to submit a user message to a chat session."""
    message: str = Field(..., min_length=1, description="User prompt text")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Inference sampling temperature")


class MessageResponse(BaseModel):
    """Response model for single non-streaming completion."""
    session_id: str
    user_message: str
    assistant_response: str
    
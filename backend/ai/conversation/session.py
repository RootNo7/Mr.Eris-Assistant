"""
ERIS Conversation Session Management.
Handles session state, message history, and context tracking.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from backend.providers.base import ChatMessage, MessageRole


class ChatSession(BaseModel):
    """Represents an active dialogue session containing history and metadata."""
    session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), 
        description="Unique session identifier"
    )
    title: str = Field(default="New Session", description="Display title for the conversation")
    messages: List[ChatMessage] = Field(
        default_factory=list, 
        description="Ordered message history"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Last activity timestamp"
    )
    system_prompt: Optional[str] = Field(
        default="You are ERIS (Evolutionary Responsive Intelligent System), a modular Personal AI Operating System.",
        description="Active system instruction for this session"
    )

    def add_message(self, role: MessageRole, content: str) -> ChatMessage:
        """Appends a new message to the session context and updates timestamp."""
        msg = ChatMessage(role=role, content=content)
        self.messages.append(msg)
        self.updated_at = datetime.now(timezone.utc)
        return msg

    def get_context_payload(self) -> List[ChatMessage]:
        """Constructs the complete message history payload including system prompt."""
        payload: List[ChatMessage] = []
        if self.system_prompt:
            payload.append(ChatMessage(role=MessageRole.SYSTEM, content=self.system_prompt))
        payload.extend(self.messages)
        return payload


class SessionManager:
    """In-memory manager tracking active ChatSession instances."""

    def __init__(self) -> None:
        self._sessions: Dict[str, ChatSession] = {}

    def create_session(
        self, 
        title: str = "New Session", 
        system_prompt: Optional[str] = None
    ) -> ChatSession:
        """Creates and stores a new ChatSession."""
        session = ChatSession(
            title=title,
            system_prompt=system_prompt or "You are ERIS, a modular Personal AI Operating System."
        )
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> Optional[ChatSession]:
        """Retrieves an existing ChatSession by ID."""
        return self._sessions.get(session_id)

    def list_sessions(self) -> List[ChatSession]:
        """Returns all active sessions sorted by last updated timestamp."""
        return sorted(self._sessions.values(), key=lambda s: s.updated_at, reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Removes a session from memory."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
        
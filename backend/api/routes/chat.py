"""
ERIS Chat Endpoint Router.
Provides REST and SSE endpoints for session lifecycle and conversation management.
"""

import json
from typing import List
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import StreamingResponse

from backend.core.config import get_settings
from backend.core.exceptions import ERISError
from backend.core.logging import logger
from backend.providers.gemini import GeminiProvider
from backend.ai.conversation import SessionManager, ConversationEngine
from backend.api.schemas import (
    CreateSessionRequest,
    SessionResponse,
    SendMessageRequest,
    MessageResponse,
)

router = APIRouter(prefix="/chat", tags=["Chat"])

# Global in-memory session manager instance
session_manager = SessionManager()


def get_conversation_engine() -> ConversationEngine:
    """Dependency provider initializing ConversationEngine with active GeminiProvider."""
    settings = get_settings()
    provider = GeminiProvider(
        api_key=settings.GEMINI_API_KEY,
        default_model=settings.DEFAULT_GEMINI_MODEL,
    )
    return ConversationEngine(provider=provider)


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: CreateSessionRequest):
    """Creates a new chat session."""
    session = session_manager.create_session(
        title=request.title,
        system_prompt=request.system_prompt
    )
    return SessionResponse(
        session_id=session.session_id,
        title=session.title,
        message_count=len(session.messages),
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


@router.get("/sessions", response_model=List[SessionResponse])
async def list_sessions():
    """Retrieves all active chat sessions."""
    sessions = session_manager.list_sessions()
    return [
        SessionResponse(
            session_id=s.session_id,
            title=s.title,
            message_count=len(s.messages),
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s in sessions
    ]


@router.post("/sessions/{session_id}/message", response_model=MessageResponse)
async def send_message(
    session_id: str,
    payload: SendMessageRequest,
    engine: ConversationEngine = Depends(get_conversation_engine),
):
    """Sends a user message and returns the complete AI response synchronously."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    try:
        response_text = await engine.process_message(
            session=session,
            user_content=payload.message,
            temperature=payload.temperature,
        )
        return MessageResponse(
            session_id=session_id,
            user_message=payload.message,
            assistant_response=response_text,
        )
    except ERISError as e:
        logger.error(f"API send_message error: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/sessions/{session_id}/stream")
async def stream_message(
    session_id: str,
    payload: SendMessageRequest,
    engine: ConversationEngine = Depends(get_conversation_engine),
):
    """Sends a user message and streams the response via Server-Sent Events (SSE)."""
    session = session_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found.")

    async def event_generator():
        try:
            async for chunk in engine.stream_message(
                session=session,
                user_content=payload.message,
                temperature=payload.temperature,
            ):
                data_payload = json.dumps({"delta": chunk})
                yield f"data: {data_payload}\n\n"
            yield "data: [DONE]\n\n"
        except ERISError as e:
            logger.error(f"API stream_message error: {e}")
            error_payload = json.dumps({"error": str(e)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
    
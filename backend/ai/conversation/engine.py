"""
ERIS Conversation Engine.
Orchestrates dialogue flow between ChatSessions and active AI Providers.
"""

from typing import AsyncGenerator

from backend.core.exceptions import ProviderError
from backend.core.logging import logger
from backend.providers.base import BaseAIProvider, LLMRequest, MessageRole
from backend.ai.conversation.session import ChatSession


class ConversationEngine:
    """Core engine routing session messages through a provider abstraction interface."""

    def __init__(self, provider: BaseAIProvider) -> None:
        self.provider = provider

    async def process_message(
        self, 
        session: ChatSession, 
        user_content: str,
        temperature: float = 0.7
    ) -> str:
        """
        Executes a single non-streaming dialogue exchange.
        Updates session history with user message and AI response.
        """
        session.add_message(role=MessageRole.USER, content=user_content)

        payload = session.get_context_payload()
        request = LLMRequest(messages=payload, temperature=temperature)

        try:
            response = await self.provider.generate(request)
            session.add_message(role=MessageRole.ASSISTANT, content=response.content)
            return response.content
        except ProviderError as e:
            logger.error(f"Conversation engine failure during message processing: {e}")
            raise

    async def stream_message(
        self, 
        session: ChatSession, 
        user_content: str,
        temperature: float = 0.7
    ) -> AsyncGenerator[str, None]:
        """
        Executes a streaming dialogue exchange.
        Yields text deltas and updates session history once generation completes.
        """
        session.add_message(role=MessageRole.USER, content=user_content)

        payload = session.get_context_payload()
        request = LLMRequest(messages=payload, temperature=temperature)

        accumulated_text = ""

        try:
            async for chunk in self.provider.stream(request):
                if chunk.delta:
                    accumulated_text += chunk.delta
                    yield chunk.delta

            if accumulated_text:
                session.add_message(role=MessageRole.ASSISTANT, content=accumulated_text)

        except ProviderError as e:
            logger.error(f"Conversation engine failure during streaming: {e}")
            raise
            
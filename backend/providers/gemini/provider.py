"""
ERIS Google Gemini Provider Implementation.
Integrates Google Gemini API using the official google-genai SDK.
"""

from typing import AsyncGenerator, List, Optional, Tuple
from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.core.exceptions import ProviderAPIError, ProviderInitializationError
from backend.core.logging import logger
from backend.providers.base import (
    BaseAIProvider,
    ChatMessage,
    LLMRequest,
    LLMResponse,
    MessageRole,
    ProviderCapabilities,
    StreamChunk,
)


class GeminiProvider(BaseAIProvider):
    """Concrete AI Provider implementation for Google Gemini."""

    def __init__(self, api_key: str, default_model: str = "gemini-2.5-flash") -> None:
        super().__init__(api_key=api_key, default_model=default_model)
        if not api_key:
            raise ProviderInitializationError("Gemini API key cannot be empty.")

        try:
            self.client = genai.Client(api_key=self.api_key)
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise ProviderInitializationError(
                message="Failed to initialize Google Gemini client instance",
                details={"error": str(e)}
            ) from e

    def _prepare_payload(
        self, request: LLMRequest
    ) -> Tuple[Optional[str], List[types.Content], types.GenerateContentConfig]:
        """Translates unified ERIS LLMRequest models into Gemini SDK parameters."""
        system_instruction: Optional[str] = None
        contents: List[types.Content] = []

        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                if system_instruction:
                    system_instruction += f"\n{msg.content}"
                else:
                    system_instruction = msg.content
            else:
                role_map = {
                    MessageRole.USER: "user",
                    MessageRole.ASSISTANT: "model",
                }
                gemini_role = role_map.get(msg.role, "user")
                contents.append(
                    types.Content(
                        role=gemini_role,
                        parts=[types.Part.from_text(text=msg.content)]
                    )
                )

        config = types.GenerateContentConfig(
            temperature=request.temperature,
            top_p=request.top_p,
            max_output_tokens=request.max_tokens,
            stop_sequences=request.stop_sequences,
            system_instruction=system_instruction,
        )

        return system_instruction, contents, config

    async def generate(self, request: LLMRequest) -> LLMResponse:
        """Executes a single async prompt generation request."""
        model = self.default_model
        _, contents, config = self._prepare_payload(request)

        try:
            response = await self.client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

            usage = response.usage_metadata
            prompt_tokens = usage.prompt_token_count if usage else 0
            completion_tokens = usage.candidates_token_count if usage else 0

            finish_reason = None
            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = str(response.candidates[0].finish_reason)

            return LLMResponse(
                content=response.text or "",
                model_name=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                finish_reason=finish_reason,
                raw_response={"response_id": getattr(response, "response_id", None)}
            )

        except APIError as e:
            logger.error(f"Gemini API generation error: {e}")
            raise ProviderAPIError(
                message="Gemini API generation request failed",
                details={"error": str(e), "code": getattr(e, "code", None)}
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error during Gemini inference: {e}")
            raise ProviderAPIError(
                message="Unexpected error during Gemini response generation",
                details={"error": str(e)}
            ) from e

    async def stream(
        self, request: LLMRequest
    ) -> AsyncGenerator[StreamChunk, None]:
        """Executes real-time token response streaming."""
        model = self.default_model
        _, contents, config = self._prepare_payload(request)

        try:
            async for chunk in await self.client.aio.models.generate_content_stream(
                model=model,
                contents=contents,
                config=config,
            ):
                finish_reason = None
                if chunk.candidates and chunk.candidates[0].finish_reason:
                    finish_reason = str(chunk.candidates[0].finish_reason)

                yield StreamChunk(
                    delta=chunk.text or "",
                    finish_reason=finish_reason,
                )

        except APIError as e:
            logger.error(f"Gemini API streaming error: {e}")
            raise ProviderAPIError(
                message="Gemini API streaming request failed",
                details={"error": str(e)}
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error during Gemini streaming: {e}")
            raise ProviderAPIError(
                message="Unexpected error during Gemini response streaming",
                details={"error": str(e)}
            ) from e

    async def validate_credentials(self) -> bool:
        """Validates provider API credentials with a minimal request check."""
        try:
            test_request = LLMRequest(
                messages=[ChatMessage(role=MessageRole.USER, content="ping")]
            )
            await self.generate(test_request)
            return True
        except Exception as e:
            logger.warning(f"Gemini credential validation check failed: {e}")
            return False

    def get_capabilities(self) -> ProviderCapabilities:
        """Returns capabilities metadata supported by Google Gemini."""
        return ProviderCapabilities(
            provider_name="gemini",
            supports_streaming=True,
            supports_tools=True,
            supports_vision=True,
            supported_models=["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
        )
        
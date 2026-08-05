"""
ERIS Abstract Base Provider Interface.
Defines the architectural contract that all AI provider implementations must implement.
"""

from abc import ABC, abstractmethod
from typing import AsyncGenerator

from backend.providers.base.models import (
    LLMRequest,
    LLMResponse,
    StreamChunk,
    ProviderCapabilities,
)


class BaseAIProvider(ABC):
    """Abstract base class establishing the contract for all AI providers."""

    def __init__(self, api_key: str, default_model: str) -> None:
        self.api_key = api_key
        self.default_model = default_model

    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        """
        Executes a synchronous-style single prompt generation.

        :param request: Standardized LLMRequest configuration object.
        :return: Standardized LLMResponse object.
        """
        pass

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncGenerator[StreamChunk, None]:
        """
        Executes real-time token streaming generation.

        :param request: Standardized LLMRequest configuration object.
        :yield: StreamChunk containing incremental text response frames.
        """
        pass

    @abstractmethod
    async def validate_credentials(self) -> bool:
        """
        Verifies provider authentication credentials and API access.

        :return: True if credentials are valid, False otherwise.
        """
        pass

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """
        Retrieves feature capabilities supported by this provider instance.

        :return: ProviderCapabilities metadata object.
        """
        pass
        
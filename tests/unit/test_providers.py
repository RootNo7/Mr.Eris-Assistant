import pytest
from unittest.mock import MagicMock, patch
from backend.core.config.settings import Config
from backend.providers.gemini.provider import GeminiProvider


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.GEMINI_API_KEY = "test_key"
    return config


@patch("backend.providers.gemini.provider.genai.Client")
def test_gemini_provider_initialization(mock_genai_client, mock_config):
    provider = GeminiProvider(config=mock_config)
    mock_genai_client.assert_called_once_with(api_key="test_key")
    assert provider.model_name == "gemini-3.5-flash"


@patch("backend.providers.gemini.provider.genai.Client")
def test_gemini_provider_generate_response(mock_genai_client, mock_config):
    # Mock response object
    mock_response = MagicMock()
    mock_response.text = "Test response from Gemini"

    # Mock client instance and method chain
    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content.return_value = mock_response
    mock_genai_client.return_value = mock_client_instance

    provider = GeminiProvider(config=mock_config)
    result = provider.generate_response("Hello")

    mock_client_instance.models.generate_content.assert_called_once()
    call_kwargs = mock_client_instance.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.5-flash"
    assert result == "Test response from Gemini"


@patch("backend.providers.gemini.provider.genai.Client")
def test_gemini_provider_rejects_empty_prompt(mock_genai_client, mock_config):
    provider = GeminiProvider(config=mock_config)
    with pytest.raises(ValueError):
        provider.generate_response("   ")


@patch("backend.providers.gemini.provider.genai.Client")
def test_gemini_provider_generate_response_stream(mock_genai_client, mock_config):
    # Mock the stream generator chunks
    chunk1, chunk2 = MagicMock(), MagicMock()
    chunk1.text = "Hello "
    chunk2.text = "World!"
    
    mock_client_instance = MagicMock()
    mock_client_instance.models.generate_content_stream.return_value = [chunk1, chunk2]
    mock_genai_client.return_value = mock_client_instance
    
    provider = GeminiProvider(config=mock_config)
    
    # Consume the generator stream
    chunks = list(provider.generate_response_stream("Hello"))
    
    assert len(chunks) == 2
    assert chunks[0] == "Hello "
    assert chunks[1] == "World!"
import pytest
from unittest.mock import MagicMock, patch
from backend.providers.openrouter.provider import OpenRouterProvider
from backend.core.exceptions import ProviderInitializationError


@pytest.fixture
def mock_openrouter_config():
    config = MagicMock()
    config.OPENROUTER_API_KEY = "test_openrouter_key"
    config.OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
    return config


@patch("backend.providers.openrouter.provider.openai.OpenAI")
def test_openrouter_provider_initialization(mock_openai_client, mock_openrouter_config):
    provider = OpenRouterProvider(config=mock_openrouter_config)
    mock_openai_client.assert_called_once_with(
        base_url="https://openrouter.ai/api/v1",
        api_key="test_openrouter_key",
        default_headers={
            "HTTP-Referer": "https://github.com/Hafiz-Faisal902/Mr.Eris-Assistant",
            "X-Title": "ERIS Digital Assistant",
        }
    )
    assert provider.model_name == "meta-llama/llama-3.3-70b-instruct:free"


def test_openrouter_provider_missing_api_key():
    config = MagicMock()
    config.OPENROUTER_API_KEY = None
    config.OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
    
    with pytest.raises(ProviderInitializationError, match="OPENROUTER_API_KEY must be provided"):
        OpenRouterProvider(config=config)


@patch("backend.providers.openrouter.provider.openai.OpenAI")
def test_openrouter_provider_rejects_empty_prompt(mock_openai_client, mock_openrouter_config):
    provider = OpenRouterProvider(config=mock_openrouter_config)
    with pytest.raises(ValueError, match="Prompt cannot be empty"):
        provider.generate_response("   ")


@patch("backend.providers.openrouter.provider.openai.OpenAI")
def test_openrouter_provider_generate_response(mock_openai_client, mock_openrouter_config):
    mock_choice = MagicMock()
    mock_choice.message.content = "OpenRouter test response"
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create.return_value = mock_response
    mock_openai_client.return_value = mock_client_instance

    provider = OpenRouterProvider(config=mock_openrouter_config)
    result = provider.generate_response("Hello OpenRouter")

    mock_client_instance.chat.completions.create.assert_called_once_with(
        model="meta-llama/llama-3.3-70b-instruct:free",
        messages=[{"role": "user", "content": "Hello OpenRouter"}]
    )
    assert result == "OpenRouter test response"


@patch("backend.providers.openrouter.provider.openai.OpenAI")
def test_openrouter_provider_generate_response_stream(mock_openai_client, mock_openrouter_config):
    chunk1, chunk2 = MagicMock(), MagicMock()
    chunk1.choices = [MagicMock(delta=MagicMock(content="Hello "))]
    chunk2.choices = [MagicMock(delta=MagicMock(content="World!"))]

    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create.return_value = [chunk1, chunk2]
    mock_openai_client.return_value = mock_client_instance

    provider = OpenRouterProvider(config=mock_openrouter_config)
    chunks = list(provider.generate_response_stream("Hello Stream"))

    assert len(chunks) == 2
    assert chunks[0] == "Hello "
    assert chunks[1] == "World!"


@patch("backend.providers.openrouter.provider.openai.OpenAI")
def test_openrouter_provider_with_tool_registry(mock_openai_client, mock_openrouter_config):
    mock_registry = MagicMock()
    mock_registry.get_openai_schemas.return_value = [{"type": "function", "function": {"name": "test_tool"}}]
    
    mock_choice = MagicMock()
    mock_choice.message.tool_calls = None
    mock_choice.message.content = "Response with tools registered"
    
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    
    mock_client_instance = MagicMock()
    mock_client_instance.chat.completions.create.return_value = mock_response
    mock_openai_client.return_value = mock_client_instance

    provider = OpenRouterProvider(config=mock_openrouter_config, tool_registry=mock_registry)
    result = provider.generate_response("Test with tool")

    assert result == "Response with tools registered"
    mock_client_instance.chat.completions.create.assert_called_once_with(
        model="meta-llama/llama-3.3-70b-instruct:free",
        messages=[{"role": "user", "content": "Test with tool"}],
        tools=[{"type": "function", "function": {"name": "test_tool"}}]
    )


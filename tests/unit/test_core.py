import os
import pytest
import logging
from backend.core.config.settings import Config
from backend.core.exceptions import ConfigurationError
from backend.core.logging.logger import get_logger

def test_config_loads_variables(monkeypatch):
    """Verifies that the Config class correctly maps environment variables."""
    monkeypatch.setenv("ACTIVE_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test_mock_key")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    
    config = Config()
    assert config.GEMINI_API_KEY == "test_mock_key"
    assert config.ACTIVE_PROVIDER == "gemini"

def test_config_validation_fails_safely(monkeypatch):
    """Verifies that ERIS refuses to boot if the active provider API key is missing."""
    monkeypatch.setenv("ACTIVE_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    
    with pytest.raises(ConfigurationError, match="GEMINI_API_KEY is missing"):
        Config()

def test_logger_initialization():
    """Verifies the logger utility initializes and formats correctly."""
    test_logger = get_logger("test_module")
    
    assert isinstance(test_logger, logging.Logger)
    assert test_logger.name == "test_module"
    assert len(test_logger.handlers) > 0
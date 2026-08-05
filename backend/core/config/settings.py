"""
ERIS System Configuration Schema.
Defines strongly typed application settings and environment loader.
"""

from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core settings schema for ERIS system kernel."""

    # Environment Configuration
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = Field(
        default="development",
        description="Active application operational state"
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO",
        description="System logging output threshold"
    )

    # Cloud AI Intelligence Provider Settings
    GEMINI_API_KEY: str = Field(
        ...,
        description="Google Gemini Cloud API key credential"
    )
    DEFAULT_GEMINI_MODEL: str = Field(
        default="gemini-2.5-flash",
        description="Default Gemini model tier for primary inference"
    )

    # API Server Settings
    API_V1_STR: str = Field(
        default="/api/v1",
        description="API endpoint namespace prefix"
    )
    PROJECT_NAME: str = Field(
        default="ERIS Personal AI OS",
        description="Application core name"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True
    )
    
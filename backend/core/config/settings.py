import os
from dotenv import load_dotenv
from backend.core.exceptions import ConfigurationError

# Load variables from the .env file into the environment
load_dotenv()


class Config:
    """
    Centralized configuration for ERIS.
    Ensures secrets, security posture, and filesystem guard options are loaded safely.
    """

    DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"

    def __init__(self):
        self.ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
        self.LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
        self.ACTIVE_PROVIDER = os.getenv("ACTIVE_PROVIDER", "gemini").lower()
        self.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        self.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
        self.OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", self.DEFAULT_OPENROUTER_MODEL)
        self.ERIS_AUTH_ENABLED = os.getenv("ERIS_AUTH_ENABLED", "false").lower() in ("true", "1", "yes")
        self.ERIS_API_KEY = os.getenv("ERIS_API_KEY")

        # Action Permission Framework & Filesystem Guard Settings
        self.ERIS_SECURITY_MODE = os.getenv("ERIS_SECURITY_MODE", "balanced").lower()
        self.ERIS_MAX_AUTO_RISK = os.getenv("ERIS_MAX_AUTO_RISK", "T1").upper()
        self.ERIS_ALLOWED_FS_ROOTS = os.getenv("ERIS_ALLOWED_FS_ROOTS", os.getcwd())
        
        try:
            self.ERIS_TOOL_TIMEOUT = float(os.getenv("ERIS_TOOL_TIMEOUT", "15.0"))
        except ValueError:
            self.ERIS_TOOL_TIMEOUT = 15.0

        try:
            self.ERIS_MAX_FILE_SIZE_BYTES = int(os.getenv("ERIS_MAX_FILE_SIZE_BYTES", "10485760"))
        except ValueError:
            self.ERIS_MAX_FILE_SIZE_BYTES = 10485760

        self.validate()

    def validate(self):
        """Validates that strictly required environment variables are present."""
        if self.ACTIVE_PROVIDER == "gemini" and not self.GEMINI_API_KEY:
            raise ConfigurationError("GEMINI_API_KEY is missing from the environment.")
        elif self.ACTIVE_PROVIDER == "openrouter" and not self.OPENROUTER_API_KEY:
            raise ConfigurationError("OPENROUTER_API_KEY is missing from the environment.")

        if self.ERIS_AUTH_ENABLED and not self.ERIS_API_KEY:
            raise ConfigurationError("ERIS_AUTH_ENABLED is True but ERIS_API_KEY is missing from the environment.")

    @property
    def environment(self) -> str:
        return self.ENVIRONMENT

    @property
    def log_level(self) -> str:
        return self.LOG_LEVEL

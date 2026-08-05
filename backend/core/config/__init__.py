"""
ERIS Core Configuration Package Initialization.
"""

from functools import lru_cache
from backend.core.config.settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Factory function providing a cached instance of the system settings.
    
    :return: Singleton Settings object instance.
    """
    return Settings()


__all__ = ["Settings", "get_settings"]

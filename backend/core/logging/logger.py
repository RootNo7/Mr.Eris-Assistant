"""
ERIS Structured Logging Subsystem.
Configures system-wide logging channels connected to application settings.
"""

import logging
import sys
from typing import Optional

from backend.core.config import get_settings


def setup_logger(name: str = "ERIS") -> logging.Logger:
    """
    Factory function providing a configured logger instance.

    :param name: Namespace identifier for the logger instance.
    :return: Formatted logging.Logger object.
    """
    settings = get_settings()
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if re-initialized
    if not logger.handlers:
        logger.setLevel(settings.LOG_LEVEL)

        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.propagate = False

    return logger


# Primary logger instance for core kernel initialization
logger = setup_logger("ERIS.Kernel")

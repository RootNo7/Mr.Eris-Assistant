import logging
import sys

from backend.core.config.settings import Config


def get_logger(name: str = "ERIS") -> logging.Logger:
    """
    Returns a configured logger instance for the given module name.
    Ensures consistent formatting, a single handler (no duplicate log lines
    on repeated calls), and a log level driven by Config.LOG_LEVEL — falling
    back safely to INFO if that value is missing or invalid.
    """
    logger_instance = logging.getLogger(name)

    if not logger_instance.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger_instance.addHandler(handler)

        level_name = (getattr(Config, "LOG_LEVEL", None) or "INFO").upper()
        level = logging.getLevelName(level_name)
        # logging.getLevelName() returns a string like "Level X" for an
        # unrecognized name instead of raising — guard against that so a
        # typo'd LOG_LEVEL in .env can never crash startup.
        if not isinstance(level, int):
            level = logging.INFO
        logger_instance.setLevel(level)

    return logger_instance


# Backward-compatible alias — earlier ERIS code called this "setup_logger".
setup_logger = get_logger

# Centralized module-level logger instance exported across ERIS.
logger = get_logger("ERIS")

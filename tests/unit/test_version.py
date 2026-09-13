import re
import pytest
from backend.core.version import __version__, VERSION

def test_version_exports():
    """Verify __version__ and VERSION are non-empty strings and equal."""
    assert isinstance(__version__, str)
    assert isinstance(VERSION, str)
    assert __version__ == VERSION
    assert __version__ == "2.9.1"

def test_version_format():
    """Verify semantic versioning format (e.g. X.Y.Z)."""
    pattern = r"^\d+\.\d+\.\d+(-[a-zA-Z0-9.]+)?$"
    assert re.match(pattern, VERSION) is not None

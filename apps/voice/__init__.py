"""
apps/voice/__init__.py

Voice Assistant Application Package.
Exposes the CLI runner for the ERIS Voice Assistant Daemon.
"""

from apps.voice.main import main

__all__ = ["main"]

"""
backend/voice/vad.py

Voice Activity Detection (VAD) Engines for ERIS Voice Subsystem (v2.7.0).

Provides:
- EnergyVADEngine: RMS energy-based voice activity detection algorithm
- MockVADEngine: Injectable mock VAD engine for unit testing
"""

from __future__ import annotations

import math
import struct
from backend.voice.base import VADEngine
from backend.voice.models import AudioChunk


class MockVADEngine(VADEngine):
    """
    Mock VAD engine for unit tests.
    Can be configured to report speech or silence deterministically.
    """

    def __init__(self, speech_pattern: bool = True, always_speech: Optional[bool] = None, **kwargs):
        if always_speech is not None:
            self.speech_pattern = always_speech
        else:
            self.speech_pattern = speech_pattern
        self._call_count = 0

    def set_speech(self, is_speech: bool) -> None:
        self.speech_pattern = is_speech

    def is_speech(self, chunk: AudioChunk) -> bool:
        self._call_count += 1
        return self.speech_pattern


class EnergyVADEngine(VADEngine):
    """
    RMS Energy-based VAD engine.
    Calculates Root-Mean-Square (RMS) amplitude of PCM 16-bit audio frames and
    compares against configurable energy threshold.
    """

    def __init__(self, energy_threshold: float = 0.02):
        self.energy_threshold = energy_threshold

    def calculate_rms(self, chunk: AudioChunk) -> float:
        data = chunk.data
        if not data or len(data) < 2:
            return 0.0

        count = len(data) // 2
        shorts = struct.unpack(f"<{count}h", data[:count*2])
        sum_squares = sum(s * s for s in shorts)
        mean_square = sum_squares / count
        rms_raw = math.sqrt(mean_square)
        # Normalize RMS relative to 16-bit max int (32767)
        return rms_raw / 32767.0

    def is_speech(self, chunk: AudioChunk) -> bool:
        rms = self.calculate_rms(chunk)
        return rms >= self.energy_threshold

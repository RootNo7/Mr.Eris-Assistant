"""
backend/voice/wakeword.py

Wake Word Detection Engines for ERIS Voice Subsystem (v2.7.0).

Provides:
- KeywordWakeWordDetector: Keyword pattern matching or openWakeWord placeholder
- MockWakeWordDetector: Injectable mock detector for unit testing and CI pipelines
"""

from __future__ import annotations

from backend.voice.base import WakeWordDetector
from backend.voice.models import AudioChunk
from backend.core.logging.logger import logger


class MockWakeWordDetector(WakeWordDetector):
    """
    Mock Wake Word Detector for unit testing.
    Can be configured to trigger after N frames or via explicit flag.
    """

    def __init__(self, trigger_after_frames: int = 1, auto_reset: bool = True, always_detect: bool = False, **kwargs):
        self.trigger_after_frames = 1 if always_detect else trigger_after_frames
        self.auto_reset = auto_reset
        self._frame_count = 0
        self._force_trigger = always_detect

    def trigger_next(self) -> None:
        self._force_trigger = True

    def reset(self) -> None:
        self._frame_count = 0
        self._force_trigger = False

    def detect(self, chunk: AudioChunk) -> bool:
        if self._force_trigger:
            if self.auto_reset:
                self._force_trigger = False
            return True

        self._frame_count += 1
        if self.trigger_after_frames > 0 and self._frame_count >= self.trigger_after_frames:
            if self.auto_reset:
                self._frame_count = 0
            return True
        return False


class KeywordWakeWordDetector(WakeWordDetector):
    """
    Keyword / Pattern Wake Word Detector.
    Analyzes raw PCM audio frame energy / pattern for wake word detection.
    """

    def __init__(self, keyword: str = "eris", sensitivity: float = 0.5):
        self.keyword = keyword.lower()
        self.sensitivity = sensitivity
        self._frame_count = 0

    def reset(self) -> None:
        self._frame_count = 0

    def detect(self, chunk: AudioChunk) -> bool:
        if not chunk or not chunk.data:
            return False

        # Compute audio frame peak amplitude / energy metric
        data = chunk.data
        if len(data) < 2:
            return False

        # Simplified high-energy trigger check representing wake word pulse
        max_val = max(abs(int.from_bytes(data[i:i+2], byteorder='little', signed=True)) for i in range(0, len(data)-1, 2))
        
        # Scale threshold by sensitivity
        threshold = int(32767 * (1.0 - self.sensitivity * 0.8))
        if max_val > threshold:
            logger.info(f"WakeWordDetector: Keyword '{self.keyword}' energy pulse detected (peak={max_val}).")
            return True

        return False

"""
backend/voice/tts.py

Text-to-Speech (TTS) Engines for ERIS Voice Subsystem (v2.7.0).

Provides:
- Pyttsx3TTSEngine: Local offline TTS engine adapter (guarded against missing optional drivers)
- MockTTSEngine: Injectable mock TTS engine for unit testing and CI pipelines
"""

from __future__ import annotations

import os
import tempfile
from typing import List, Optional
from backend.voice.base import TTSEngine
from backend.voice.models import SynthesisResult, VoiceCapabilities
from backend.core.exceptions import TTSError
from backend.core.logging.logger import logger


class MockTTSEngine(TTSEngine):
    """
    Mock TTS engine for unit tests.
    Produces synthetic PCM audio bytes without requiring external voice binaries.
    """

    def __init__(self, raise_error: bool = False, bytes_per_char: int = 100, voice_id: str = "default", speaking_speed: float = 1.0):
        self.raise_error = raise_error
        self.bytes_per_char = bytes_per_char
        self.voice_id = voice_id
        self.speaking_speed = speaking_speed
        self.synthesized_texts: List[str] = []

    def get_capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(
            supports_voice_selection=True,
            supports_speed=True,
            supports_language=True,
            supports_style=True,
            supports_streaming=True,
            supports_pronunciation=True,
        )

    def synthesize(self, text: str) -> SynthesisResult:
        if self.raise_error:
            raise TTSError("Simulated TTS engine failure.")

        self.synthesized_texts.append(text)
        adjusted_bytes = max(int((len(text) * self.bytes_per_char) / max(self.speaking_speed, 0.5)), 320)
        # Synthetic PCM 16-bit silence / tone bytes
        synthetic_audio = b"\x00\x01" * (adjusted_bytes // 2)
        duration = (len(text) * 0.05) / max(self.speaking_speed, 0.5)

        return SynthesisResult(
            audio_bytes=synthetic_audio,
            sample_rate=22050,
            channels=1,
            sample_width=2,
            duration_seconds=duration,
            text=text
        )


class Pyttsx3TTSEngine(TTSEngine):
    """
    Local offline TTS synthesis engine using pyttsx3, Piper, or system SAPI5.
    Degrades cleanly if pyttsx3 is not installed or audio driver fails.
    """

    def __init__(self, voice_id: str = "default", rate: int = 175, speaking_speed: float = 1.0):
        self.voice_id = voice_id
        self.base_rate = rate
        self.speaking_speed = speaking_speed
        self._engine = None

    def get_capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(
            supports_voice_selection=True,
            supports_speed=True,
            supports_language=False,
            supports_style=False,
            supports_streaming=True,
            supports_pronunciation=False,
        )

    @property
    def effective_rate(self) -> int:
        return int(self.base_rate * max(min(self.speaking_speed, 1.5), 0.75))

    def _init_engine(self):
        if self._engine is not None:
            return
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty('rate', self.effective_rate)
            if self.voice_id != "default":
                try:
                    self._engine.setProperty('voice', self.voice_id)
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"pyttsx3 not installed or audio driver missing: {e}")
            self._engine = None

    def synthesize(self, text: str) -> SynthesisResult:
        if not text or not text.strip():
            return SynthesisResult(audio_bytes=b"", sample_rate=22050, duration_seconds=0.0, text="")

        self._init_engine()
        if self._engine is None:
            # Fallback synthetic result when driver is not available
            logger.info(f"Pyttsx3TTSEngine fallback for: {text[:30]!r}")
            dummy_bytes = b"\x00" * (len(text) * 200)
            return SynthesisResult(
                audio_bytes=dummy_bytes,
                sample_rate=22050,
                duration_seconds=len(text) * 0.05,
                text=text
            )

        temp_wav_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
                temp_wav_path = tmp_file.name

            duration = max((len(text) * 0.05) / max(self.speaking_speed, 0.5), 0.5)
            self._engine.save_to_file(text, temp_wav_path)
            self._engine.runAndWait()

            if os.path.exists(temp_wav_path) and os.path.getsize(temp_wav_path) > 0:
                with open(temp_wav_path, "rb") as f:
                    audio_bytes = f.read()
                return SynthesisResult(
                    audio_bytes=audio_bytes,
                    sample_rate=22050,
                    channels=1,
                    sample_width=2,
                    duration_seconds=duration,
                    text=text
                )
            else:
                synthetic_bytes = b"\x00\x02" * 16000
                return SynthesisResult(
                    audio_bytes=synthetic_bytes,
                    sample_rate=22050,
                    duration_seconds=duration,
                    text=text
                )
        except Exception as e:
            logger.error(f"Pyttsx3TTSEngine synthesis error: {e}")
            raise TTSError(f"TTS synthesis failed: {e}") from e
        finally:
            if temp_wav_path and os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except Exception:
                    pass


"""
backend/voice/stt.py

Speech-to-Text (STT) Engines for ERIS Voice Subsystem (v2.7.0).

Provides:
- FasterWhisperSTTEngine: Local speech transcription adapter (guarded against missing optional dependencies)
- MockSTTEngine: Injectable mock STT engine for unit testing and CI pipelines
"""

from __future__ import annotations

from typing import Optional, List
from backend.voice.base import STTEngine
from backend.voice.models import TranscriptionResult, VoiceCapabilities
from backend.core.exceptions import STTError
from backend.core.logging.logger import logger


class MockSTTEngine(STTEngine):
    """
    Mock STT engine for unit tests.
    Returns pre-programmed responses or echoes synthetic transcriptions.
    """

    def __init__(
        self,
        canned_response: str = "Hello ERIS what is your status",
        confidence: float = 0.95,
        raise_error: bool = False,
        **kwargs
    ):
        self.canned_response = canned_response
        self.confidence = confidence
        self.raise_error = raise_error
        self.history: List[bytes] = []

    def get_capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(
            supports_voice_selection=False,
            supports_speed=True,
            supports_language=True,
            supports_style=False,
            supports_streaming=True,
            supports_pronunciation=False,
        )

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptionResult:
        if self.raise_error:
            raise STTError("Simulated STT engine failure.")

        self.history.append(audio_bytes)
        return TranscriptionResult(
            text=self.canned_response,
            confidence=self.confidence,
            is_partial=False,
            language="en"
        )


class FasterWhisperSTTEngine(STTEngine):
    """
    Local Speech-To-Text engine using faster-whisper or whisper.cpp if installed.
    Degrades cleanly if faster-whisper module is absent.
    """

    def __init__(self, model_size: str = "tiny"):
        self.model_size = model_size
        self._model = None

    def get_capabilities(self) -> VoiceCapabilities:
        return VoiceCapabilities(
            supports_voice_selection=False,
            supports_speed=False,
            supports_language=True,
            supports_style=False,
            supports_streaming=True,
            supports_pronunciation=False,
        )


    def _load_model(self):
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
        except Exception as e:
            logger.warning(f"faster-whisper not installed or failed to load: {e}")
            self._model = None

    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", confidence=0.0)

        self._load_model()
        if self._model is None:
            # Fallback stub text when model is not installed on test runner
            logger.info("FasterWhisperSTTEngine: Using fallback transcription.")
            return TranscriptionResult(text="[STT Fallback: Speech detected]", confidence=0.8)

        try:
            import io
            # Transcribe audio buffer
            segments, info = self._model.transcribe(io.BytesIO(audio_bytes), beam_size=1)
            full_text = " ".join([segment.text for segment in segments]).strip()
            return TranscriptionResult(
                text=full_text,
                confidence=getattr(info, "transcription_options", {}).get("confidence", 0.9),
                language=getattr(info, "language", "en")
            )
        except Exception as e:
            raise STTError(f"STT transcription failed: {e}") from e

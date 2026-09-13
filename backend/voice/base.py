"""
backend/voice/base.py

Abstract Base Classes for the ERIS Voice Subsystem (v2.7.0).

Provides hardware-abstracted interfaces so components (Microphone, Wake Word,
VAD, STT, TTS, Speaker) can be cleanly swapped, mocked, or implemented locally.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Optional

from backend.voice.models import (
    AudioChunk,
    SynthesisResult,
    TranscriptionResult,
    VoiceCapabilities,
    VoiceConfig,
)


class AudioSource(ABC):
    """Abstract interface for audio capture devices (Microphone / Stream)."""

    @abstractmethod
    def start(self) -> None:
        """Start capturing audio."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop capturing audio."""
        pass

    @abstractmethod
    def read_chunk(self) -> Optional[AudioChunk]:
        """Read next AudioChunk frame. Returns None if audio stream ends or unavailable."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if audio input device is hardware-available."""
        pass


class WakeWordDetector(ABC):
    """Abstract interface for wake-word detection engines (e.g. openWakeWord)."""

    @abstractmethod
    def detect(self, chunk: AudioChunk) -> bool:
        """Evaluates an AudioChunk frame. Returns True if wake word is detected."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Resets internal state / buffers of detector."""
        pass


class VADEngine(ABC):
    """Abstract interface for Voice Activity Detection engines (e.g. Silero VAD)."""

    @abstractmethod
    def is_speech(self, chunk: AudioChunk) -> bool:
        """Evaluates an AudioChunk frame. Returns True if frame contains human speech."""
        pass


class STTEngine(ABC):
    """Abstract interface for Speech-to-Text engines (e.g. faster-whisper)."""

    @abstractmethod
    def transcribe(self, audio_bytes: bytes, sample_rate: int = 16000) -> TranscriptionResult:
        """Transcribe raw PCM audio bytes into text."""
        pass

    def get_capabilities(self) -> VoiceCapabilities:
        """Returns capability settings supported by this STT engine."""
        return VoiceCapabilities()


class TTSEngine(ABC):
    """Abstract interface for Text-to-Speech synthesis engines (e.g. pyttsx3, Piper, Kokoro)."""

    @abstractmethod
    def synthesize(self, text: str) -> SynthesisResult:
        """Synthesize text into speech audio bytes."""
        pass

    def get_capabilities(self) -> VoiceCapabilities:
        """Returns capability settings supported by this TTS engine."""
        return VoiceCapabilities()



class AudioPlayer(ABC):
    """Abstract interface for audio playback devices (Speaker / Output Stream)."""

    @abstractmethod
    def play(
        self,
        result: SynthesisResult,
        cancel_event: Optional[threading.Event] = None,
    ) -> bool:
        """
        Play a SynthesisResult.
        Supports cancellation mid-playback via cancel_event.
        Returns True if played completely, False if interrupted/cancelled.
        """
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop active audio playback immediately."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if audio output hardware is available."""
        pass

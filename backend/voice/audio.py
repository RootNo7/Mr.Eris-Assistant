"""
backend/voice/audio.py

Audio input/output hardware adapters for ERIS Voice Subsystem (v2.7.0).

Provides:
- SystemAudioSource: Real microphone input (guarded against missing hardware / PyAudio)
- MockAudioSource: Injectable synthetic audio stream for CI/CD and offline tests
- SystemAudioPlayer: Real speaker playback (guarded against missing hardware)
- MockAudioPlayer: Controlled mock speaker with instant or simulated playback and cancellation support
"""

from __future__ import annotations

import time
import threading
from typing import Optional, List

from backend.voice.base import AudioSource, AudioPlayer
from backend.voice.models import AudioChunk, SynthesisResult
from backend.core.exceptions import AudioHardwareError
from backend.core.logging.logger import logger


class MockAudioSource(AudioSource):
    """
    Mock AudioSource for unit tests or environments without physical microphones.
    Injects pre-programmed AudioChunks or synthetic silence/speech frames.
    """

    def __init__(
        self,
        chunks: Optional[List[AudioChunk]] = None,
        available: bool = True,
        repeat: bool = False,
        inject_speech: bool = False,
        **kwargs
    ):
        if chunks:
            self._chunks = list(chunks)
        elif inject_speech:
            self._chunks = [AudioChunk(data=b"\x00\x01" * 512, sample_rate=16000)]
            repeat = True
        else:
            self._chunks = []
        self._available = available
        self._repeat = repeat
        self._index = 0
        self._active = False

    def start(self) -> None:
        if not self._available:
            raise AudioHardwareError("Mock audio input hardware marked unavailable.")
        self._active = True
        self._index = 0

    def stop(self) -> None:
        self._active = False

    def is_available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def push_chunk(self, chunk: AudioChunk) -> None:
        self._chunks.append(chunk)

    def read_chunk(self) -> Optional[AudioChunk]:
        if not self._active or not self._available:
            return None
        if self._index < len(self._chunks):
            chunk = self._chunks[self._index]
            self._index += 1
            if self._repeat and self._index >= len(self._chunks):
                self._index = 0
            return chunk
        return None


class SystemAudioSource(AudioSource):
    """
    Real System Microphone input adapter using PyAudio or sounddevice if available.
    Degrades cleanly with AudioHardwareError if physical mic or driver is absent.
    Tracks consecutive errors to detect hardware disconnection safely.
    """

    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self._pyaudio = None
        self._stream = None
        self._active = False
        self._consecutive_errors = 0

    def is_available(self) -> bool:
        try:
            import pyaudio
            p = pyaudio.PyAudio()
            count = p.get_device_count()
            p.terminate()
            return count > 0
        except Exception:
            return False

    def start(self) -> None:
        if not self.is_available():
            raise AudioHardwareError("Microphone input device unavailable on host system.")
        try:
            import pyaudio
            self._pyaudio = pyaudio.PyAudio()
            self._stream = self._pyaudio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.sample_rate,
                input=True,
                frames_per_buffer=self.chunk_size
            )
            self._active = True
            self._consecutive_errors = 0
        except Exception as e:
            self.stop()
            raise AudioHardwareError(f"Failed to open audio input stream: {e}") from e

    def stop(self) -> None:
        self._active = False
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None

    def read_chunk(self) -> Optional[AudioChunk]:
        if not self._active or not self._stream:
            return None
        try:
            raw_data = self._stream.read(self.chunk_size, exception_on_overflow=False)
            self._consecutive_errors = 0
            return AudioChunk(data=raw_data, sample_rate=self.sample_rate)
        except Exception as e:
            self._consecutive_errors += 1
            logger.error(f"[EVENT:MIC_READ_ERROR] Error reading microphone stream (attempt {self._consecutive_errors}): {e}")
            if self._consecutive_errors >= 3:
                logger.error("[EVENT:MIC_DISCONNECTED] Microphone input stream dropped after 3 consecutive errors.")
                self._active = False
            return None


class MockAudioPlayer(AudioPlayer):
    """
    Mock AudioPlayer for unit testing or headless environments.
    Supports cancellation testing and records played synthesis results.
    Uses thread lock to serialize concurrent playback calls.
    """

    def __init__(self, available: bool = True, simulate_delay: bool = False):
        self._available = available
        self._simulate_delay = simulate_delay
        self.played_results: List[SynthesisResult] = []
        self.is_playing = False
        self._stopped = False
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        return self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            self.is_playing = False

    def play(
        self,
        result: SynthesisResult,
        cancel_event: Optional[threading.Event] = None
    ) -> bool:
        if not self._available:
            raise AudioHardwareError("Mock audio output speaker marked unavailable.")

        with self._lock:
            self.is_playing = True
            self._stopped = False

            if cancel_event and cancel_event.is_set():
                self.is_playing = False
                return False

            if self._simulate_delay:
                # Simulate chunks of playback while checking cancel_event
                duration = min(result.duration_seconds, 2.0)
                elapsed = 0.0
                step = 0.1
                while elapsed < duration:
                    if cancel_event and cancel_event.is_set():
                        self.is_playing = False
                        return False
                    if self._stopped:
                        self.is_playing = False
                        return False
                    time.sleep(step)
                    elapsed += step

            self.played_results.append(result)
            self.is_playing = False
            return True


class SystemAudioPlayer(AudioPlayer):
    """
    Real Speaker output adapter using pyttsx3 or sounddevice / winsound if available.
    Degrades cleanly if audio output device is missing.
    Uses _playback_lock to prevent overlapping play tasks.
    """

    def __init__(self):
        self._playing = False
        self._playback_lock = threading.Lock()

    def is_available(self) -> bool:
        try:
            import winsound
            return True
        except Exception:
            return False

    def stop(self) -> None:
        self._playing = False

    def play(
        self,
        result: SynthesisResult,
        cancel_event: Optional[threading.Event] = None
    ) -> bool:
        if not self.is_available():
            logger.warning("Audio output speaker device unavailable.")
            return False

        if not result.audio_bytes:
            logger.info("SystemAudioPlayer: Empty audio bytes, skipping playback.")
            return True

        with self._playback_lock:
            self._playing = True

            # Check interruption signal before starting
            if cancel_event and cancel_event.is_set():
                self._playing = False
                return False

            try:
                import winsound
                if result.audio_bytes.startswith(b"RIFF"):
                    winsound.PlaySound(result.audio_bytes, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
                else:
                    winsound.Beep(440, int(min(result.duration_seconds, 1.0) * 1000))
                self._playing = False
                return True
            except Exception as e:
                logger.error(f"[EVENT:SPEAKER_ERROR] Error playing audio on speaker: {e}")
                self._playing = False
                return False


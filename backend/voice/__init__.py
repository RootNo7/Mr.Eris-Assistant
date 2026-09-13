"""
backend/voice/__init__.py

ERIS Voice Subsystem — v2.7.0
Provides modular audio capture, wake-word detection, VAD, STT, TTS,
speaker playback, and state machine pipeline.

Public exports:
    VoicePipeline       — Main state machine manager
    VoiceConfig         — Configuration settings
    VoiceState          — Enum representing pipeline lifecycle state
    AudioChunk, TranscriptionResult, SynthesisResult — Domain models
    AudioSource, WakeWordDetector, VADEngine, STTEngine, TTSEngine, AudioPlayer — ABCs
    MockAudioSource, MockAudioPlayer, MockWakeWordDetector, MockVADEngine, MockSTTEngine, MockTTSEngine — Test doubles
"""

from backend.voice.models import (
    VoiceState,
    VoiceHealthState,
    ResponseStyle,
    ResponseVerbosity,
    VoiceCapabilities,
    VoiceProfile,
    AudioChunk,
    TranscriptionResult,
    SynthesisResult,
    VoiceConfig,
)
from backend.voice.base import (
    AudioSource,
    WakeWordDetector,
    VADEngine,
    STTEngine,
    TTSEngine,
    AudioPlayer,
)
from backend.voice.profile import VoiceProfileManager
from backend.voice.audio import (
    SystemAudioSource,
    MockAudioSource,
    SystemAudioPlayer,
    MockAudioPlayer,
)
from backend.voice.wakeword import KeywordWakeWordDetector, MockWakeWordDetector
from backend.voice.vad import EnergyVADEngine, MockVADEngine
from backend.voice.stt import FasterWhisperSTTEngine, MockSTTEngine
from backend.voice.tts import Pyttsx3TTSEngine, MockTTSEngine
from backend.voice.pipeline import VoicePipeline
from backend.voice.factory import create_production_voice_pipeline

__all__ = [
    "VoicePipeline",
    "create_production_voice_pipeline",
    "VoiceConfig",
    "VoiceState",
    "VoiceHealthState",
    "ResponseStyle",
    "ResponseVerbosity",
    "VoiceCapabilities",
    "VoiceProfile",
    "VoiceProfileManager",
    "AudioChunk",
    "TranscriptionResult",
    "SynthesisResult",
    "AudioSource",
    "WakeWordDetector",
    "VADEngine",
    "STTEngine",
    "TTSEngine",
    "AudioPlayer",
    "SystemAudioSource",
    "MockAudioSource",
    "SystemAudioPlayer",
    "MockAudioPlayer",
    "KeywordWakeWordDetector",
    "MockWakeWordDetector",
    "EnergyVADEngine",
    "MockVADEngine",
    "FasterWhisperSTTEngine",
    "MockSTTEngine",
    "Pyttsx3TTSEngine",
    "MockTTSEngine",
]


"""
backend/voice/models.py

Domain data structures for the ERIS Voice Interface Subsystem (v2.7.0).

Dataclasses and enums represent audio frames, voice pipeline state,
transcription results, speech synthesis outputs, and voice configuration.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class VoiceState(str, Enum):
    """Lifecycle state machine for the VoicePipeline (v2.8.1)."""
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    PROCESSING = "thinking"  # Alias for backward compatibility
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    ERROR = "error"


class VoiceHealthState(str, Enum):
    """Subsystem operational health state for ERIS Voice Reliability (v2.8.2)."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    RECOVERING = "recovering"


class ResponseVerbosity(str, Enum):
    """Configurable response verbosity levels for ERIS voice output (v2.8.3)."""
    CONCISE = "concise"
    NORMAL = "normal"
    DETAILED = "detailed"


class ResponseStyle(str, Enum):
    """Configurable response style/tone for ERIS voice output (v2.8.3)."""
    NEUTRAL = "neutral"
    DIRECT = "direct"
    FRIENDLY = "friendly"
    PROFESSIONAL = "professional"


@dataclass
class VoiceCapabilities:
    """Capability detection parameters exposed by TTS/STT engines (v2.8.3)."""
    supports_voice_selection: bool = True
    supports_speed: bool = True
    supports_language: bool = True
    supports_style: bool = True
    supports_streaming: bool = True
    supports_pronunciation: bool = True


@dataclass
class VoiceProfile:
    """Persistent voice profile and personalization settings (v2.8.3)."""
    id: str = "default"
    name: str = "Default Voice Profile"
    enabled: bool = True
    language: str = "en-US" #ur-PK
    locale: str = "en-US" #ur-PK
    voice_id: str = "default"
    speaking_speed: float = 1.0
    response_style: ResponseStyle = ResponseStyle.NEUTRAL
    verbosity: ResponseVerbosity = ResponseVerbosity.NORMAL
    wake_word: str = "eris"
    wake_word_enabled: bool = True
    wake_word_sensitivity: float = 0.5
    quiet_mode: bool = False
    interruption_enabled: bool = True
    streaming_enabled: bool = True
    pronunciation_dictionary: Dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize VoiceProfile to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "enabled": self.enabled,
            "language": self.language,
            "locale": self.locale,
            "voice_id": self.voice_id,
            "speaking_speed": self.speaking_speed,
            "response_style": self.response_style.value if isinstance(self.response_style, Enum) else str(self.response_style),
            "verbosity": self.verbosity.value if isinstance(self.verbosity, Enum) else str(self.verbosity),
            "wake_word": self.wake_word,
            "wake_word_enabled": self.wake_word_enabled,
            "wake_word_sensitivity": self.wake_word_sensitivity,
            "quiet_mode": self.quiet_mode,
            "interruption_enabled": self.interruption_enabled,
            "streaming_enabled": self.streaming_enabled,
            "pronunciation_dictionary": dict(self.pronunciation_dictionary),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> VoiceProfile:
        """Instantiate VoiceProfile safely from dict with default fallbacks."""
        if not isinstance(data, dict):
            return cls()
        
        style_raw = str(data.get("response_style", "neutral")).lower()
        try:
            response_style = ResponseStyle(style_raw)
        except ValueError:
            response_style = ResponseStyle.NEUTRAL

        verbosity_raw = str(data.get("verbosity", "normal")).lower()
        try:
            verbosity = ResponseVerbosity(verbosity_raw)
        except ValueError:
            verbosity = ResponseVerbosity.NORMAL

        speed = float(data.get("speaking_speed", 1.0))
        if speed < 0.75 or speed > 1.5:
            speed = 1.0

        pron_dict = data.get("pronunciation_dictionary", {})
        if not isinstance(pron_dict, dict):
            pron_dict = {}

        return cls(
            id=str(data.get("id", "default")),
            name=str(data.get("name", "Default Voice Profile")),
            enabled=bool(data.get("enabled", True)),
            language=str(data.get("language", "en-US")),
            locale=str(data.get("locale", "en-US")),
            voice_id=str(data.get("voice_id", "default")),
            speaking_speed=speed,
            response_style=response_style,
            verbosity=verbosity,
            wake_word=str(data.get("wake_word", "eris")),
            wake_word_enabled=bool(data.get("wake_word_enabled", True)),
            wake_word_sensitivity=float(data.get("wake_word_sensitivity", 0.5)),
            quiet_mode=bool(data.get("quiet_mode", False)),
            interruption_enabled=bool(data.get("interruption_enabled", True)),
            streaming_enabled=bool(data.get("streaming_enabled", True)),
            pronunciation_dictionary={str(k): str(v) for k, v in pron_dict.items() if isinstance(k, str)},
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


@dataclass
class VoiceTimeouts:
    """Explicit timeout limits (in seconds) for voice subsystem lifecycle stages."""
    mic_startup_seconds: float = 3.0
    stt_timeout_seconds: float = 10.0
    llm_timeout_seconds: float = 15.0
    tts_sentence_timeout_seconds: float = 5.0
    playback_timeout_seconds: float = 15.0


@dataclass
class VoiceRetryConfig:
    """Bounded retry parameters for transient voice subsystem operations."""
    max_retries: int = 2
    backoff_base_seconds: float = 0.1
    backoff_max_seconds: float = 0.5


@dataclass
class VoiceTurnMetrics:
    """Performance and latency metrics recorded during a voice interaction turn."""
    turn_id: str
    stt_latency_ms: float = 0.0
    llm_first_token_ms: float = 0.0
    tts_latency_ms: float = 0.0
    total_turn_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class AudioChunk:
    """Raw PCM audio frame buffer."""
    data: bytes
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2  # 16-bit PCM (2 bytes)
    timestamp: float = field(default_factory=time.time)

    @property
    def duration_seconds(self) -> float:
        """Calculate duration of audio chunk in seconds."""
        if not self.data or not self.sample_rate or not self.sample_width:
            return 0.0
        bytes_per_second = self.sample_rate * self.channels * self.sample_width
        return len(self.data) / bytes_per_second


@dataclass
class TranscriptionResult:
    """Output from Speech-to-Text (STT) engine."""
    text: str
    confidence: float = 1.0
    is_partial: bool = False
    language: str = "en"
    duration_seconds: float = 0.0


@dataclass
class SynthesisResult:
    """Output from Text-to-Speech (TTS) engine."""
    audio_bytes: bytes
    sample_rate: int = 22050
    channels: int = 1
    sample_width: int = 2
    duration_seconds: float = 0.0
    text: str = ""


@dataclass
class VoiceConfig:
    """Configuration settings for the VoicePipeline and voice engines (v2.8.3)."""
    wake_word: str = "eris"
    wake_word_sensitivity: float = 0.5
    vad_threshold: float = 0.02
    min_speech_duration_seconds: float = 0.5
    max_speech_duration_seconds: float = 15.0
    silence_timeout_seconds: float = 1.5
    sample_rate: int = 16000
    channels: int = 1
    auto_speak_response: bool = True
    stt_model_name: str = "base"
    tts_voice_id: str = "default"
    input_device: str = "default"
    output_device: str = "default"
    interruption_enabled: bool = True
    streaming_enabled: bool = True
    sentence_buffer_size: int = 1
    health_monitoring_enabled: bool = True
    quiet_mode: bool = False
    speaking_speed: float = 1.0
    response_style: ResponseStyle = ResponseStyle.NEUTRAL
    verbosity: ResponseVerbosity = ResponseVerbosity.NORMAL
    language: str = "en-US"
    profile_id: str = "default"
    pronunciation_dictionary: Dict[str, str] = field(default_factory=dict)
    timeouts: VoiceTimeouts = field(default_factory=VoiceTimeouts)
    retry_config: VoiceRetryConfig = field(default_factory=VoiceRetryConfig)

    def apply_profile(self, profile: VoiceProfile) -> None:
        """Syncs configuration attributes from a VoiceProfile."""
        self.profile_id = profile.id
        self.wake_word = profile.wake_word
        self.wake_word_sensitivity = profile.wake_word_sensitivity
        self.tts_voice_id = profile.voice_id
        self.speaking_speed = profile.speaking_speed
        self.response_style = profile.response_style
        self.verbosity = profile.verbosity
        self.language = profile.language
        self.quiet_mode = profile.quiet_mode
        self.interruption_enabled = profile.interruption_enabled
        self.streaming_enabled = profile.streaming_enabled
        self.pronunciation_dictionary = dict(profile.pronunciation_dictionary)




"""
backend/voice/factory.py

Production Voice Composition Factory for ERIS Voice Subsystem (v2.8.4).
Wires real hardware and provider adapters for live daemon execution while
preserving dependency injection for unit testing.
"""

from typing import Any, Optional

from backend.voice.audio import SystemAudioPlayer, SystemAudioSource
from backend.voice.models import VoiceConfig
from backend.voice.pipeline import VoicePipeline
from backend.voice.stt import FasterWhisperSTTEngine
from backend.voice.tts import Pyttsx3TTSEngine
from backend.voice.vad import EnergyVADEngine
from backend.voice.wakeword import KeywordWakeWordDetector


def create_production_voice_pipeline(
    engine_service: Any,
    config: Optional[VoiceConfig] = None,
    profile_manager: Optional[Any] = None,
) -> VoicePipeline:
    """
    Factory creating a production-configured VoicePipeline instance using
    real hardware and audio processing adapters (SystemAudioSource, KeywordWakeWordDetector,
    EnergyVADEngine, FasterWhisperSTTEngine, Pyttsx3TTSEngine, SystemAudioPlayer).
    """
    voice_config = config or VoiceConfig()

    audio_source = SystemAudioSource(
        sample_rate=voice_config.sample_rate,
        chunk_size=voice_config.chunk_size,
    )
    wakeword_detector = KeywordWakeWordDetector(
        keyword=voice_config.wake_word,
        sample_rate=voice_config.sample_rate,
    )
    vad_engine = EnergyVADEngine(
        energy_threshold=voice_config.vad_energy_threshold,
        sample_rate=voice_config.sample_rate,
    )
    stt_engine = FasterWhisperSTTEngine(
        model_size=voice_config.stt_model_size,
        language=voice_config.language,
    )
    tts_engine = Pyttsx3TTSEngine(
        voice_id=voice_config.voice_id,
        speaking_speed=voice_config.speaking_speed,
    )
    audio_player = SystemAudioPlayer()

    return VoicePipeline(
        engine_service=engine_service,
        audio_source=audio_source,
        wakeword_detector=wakeword_detector,
        vad_engine=vad_engine,
        stt_engine=stt_engine,
        tts_engine=tts_engine,
        audio_player=audio_player,
        config=voice_config,
        profile_manager=profile_manager,
    )

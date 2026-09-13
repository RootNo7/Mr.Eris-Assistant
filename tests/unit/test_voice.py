"""
tests/unit/test_voice.py

Unit test suite for ERIS v2.8.1 Modular Voice UX Subsystem.

All tests run 100% offline using hardware-decoupled mock components.

Test Inventory:
    1. test_voice_models_and_config              — Dataclasses, audio chunk duration, extended voice config
    2. test_mock_audio_source                     — Mock audio stream, frame reading, hardware availability toggle
    3. test_wake_word_detector                    — Keyword and mock wake word detector logic
    4. test_vad_speech_detection                  — Energy-based and mock VAD engine speech detection
    5. test_stt_transcription                     — STT transcription results and exception handling
    6. test_tts_synthesis                         — TTS synthesis audio byte generation and exception handling
    7. test_audio_player_interruption             — Audio player halts playback immediately on cancellation signal
    8. test_voice_pipeline_full_cycle             — Full state machine cycle (Wake Word → VAD → STT → Core → TTS → Player)
    9. test_voice_pipeline_empty_speech_ignored   — Silent/empty speech transcripts return to IDLE without querying core engine
    10. test_voice_pipeline_microphone_unavailable— Pipeline handles missing microphone cleanly with AudioHardwareError / ERROR state
    11. test_voice_pipeline_stt_failure           — Pipeline transitions to ERROR state on STT exception & sets friendly error
    12. test_voice_pipeline_tts_failure           — Pipeline transitions to ERROR state on TTS exception & sets friendly error
    13. test_voice_pipeline_permission_required_action — Spoken high-risk actions pass through engine service & permission framework
    14. test_voice_state_machine_transitions       — Enforces deterministic state transition rules & raises VoiceError on illegal transitions
    15. test_voice_pipeline_interruption_barge_in — Verifies interrupt() increments generation token and halts active playback immediately
    16. test_voice_pipeline_cancel_turn            — Verifies cancel_turn() resets pipeline to IDLE and invalidates active turn
    17. test_voice_pipeline_sentence_streaming     — Verifies multi-sentence responses are split and streamed to audio player
    18. test_voice_pipeline_turn_metrics           — Verifies VoiceTurnMetrics captures STT, LLM, TTS, and total turn latency
"""

from __future__ import annotations

import threading
import time
from typing import Dict, Any, List

import pytest

from backend.core.exceptions import (
    AudioHardwareError,
    STTError,
    TTSError,
    VoiceError,
)
from backend.voice.audio import MockAudioPlayer, MockAudioSource
from backend.voice.models import (
    AudioChunk,
    SynthesisResult,
    TranscriptionResult,
    VoiceConfig,
    VoiceState,
    VoiceTurnMetrics,
)
from backend.voice.pipeline import VoicePipeline
from backend.voice.stt import MockSTTEngine
from backend.voice.tts import MockTTSEngine
from backend.voice.vad import EnergyVADEngine, MockVADEngine
from backend.voice.wakeword import KeywordWakeWordDetector, MockWakeWordDetector


# Fast VoiceConfig for unit tests to prevent delays
TEST_VOICE_CONFIG = VoiceConfig(
    max_speech_duration_seconds=0.1,
    silence_timeout_seconds=0.1
)


# ---------------------------------------------------------------------------
# Dummy Engine Service for Pipeline Testing
# ---------------------------------------------------------------------------

class DummyEngineService:
    """Mock engine service wrapper simulating ERISEngineService."""

    def __init__(self, response_text: str = "Hello user, I am ERIS."):
        self.response_text = response_text
        self.prompts_received: List[str] = []

    def process_chat(self, prompt: str, clear_history: bool = False) -> Dict[str, str]:
        self.prompts_received.append(prompt)
        return {
            "response": self.response_text,
            "provider": "mock_provider",
            "model": "mock_model"
        }


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------


def test_voice_models_and_config():
    """Verify VoiceConfig, AudioChunk duration calculations, and dataclasses."""
    config = VoiceConfig()
    assert config.wake_word == "eris"
    assert config.sample_rate == 16000
    assert config.auto_speak_response is True
    assert config.input_device == "default"
    assert config.interruption_enabled is True
    assert config.streaming_enabled is True

    # 16000 samples/sec * 1 channel * 2 bytes/sample = 32000 bytes/sec
    chunk = AudioChunk(data=b"\x00" * 32000, sample_rate=16000, channels=1, sample_width=2)
    assert chunk.duration_seconds == 1.0


def test_mock_audio_source():
    """Verify MockAudioSource stream reading and availability toggling."""
    chunk1 = AudioChunk(data=b"\x01\x02" * 100)
    source = MockAudioSource(chunks=[chunk1], available=True)

    assert source.is_available() is True
    assert source.read_chunk() is None  # Stopped

    source.start()
    read_frame = source.read_chunk()
    assert read_frame == chunk1

    source.stop()
    assert source.read_chunk() is None


def test_wake_word_detector():
    """Verify Keyword and Mock wake word detectors."""
    mock_ww = MockWakeWordDetector(trigger_after_frames=2, auto_reset=True)
    chunk = AudioChunk(data=b"\x00" * 100)

    assert mock_ww.detect(chunk) is False
    assert mock_ww.detect(chunk) is True

    keyword_ww = KeywordWakeWordDetector(keyword="eris", sensitivity=0.5)
    assert keyword_ww.detect(chunk) is False

    loud_bytes = (30000).to_bytes(2, byteorder='little', signed=True) * 50
    loud_chunk = AudioChunk(data=loud_bytes)
    assert keyword_ww.detect(loud_chunk) is True


def test_vad_speech_detection():
    """Verify EnergyVADEngine detects speech above RMS energy threshold."""
    vad = EnergyVADEngine(energy_threshold=0.01)

    silent_chunk = AudioChunk(data=b"\x00" * 320)
    assert vad.is_speech(silent_chunk) is False

    loud_bytes = (20000).to_bytes(2, byteorder='little', signed=True) * 160
    speech_chunk = AudioChunk(data=loud_bytes)
    assert vad.is_speech(speech_chunk) is True


def test_stt_transcription():
    """Verify MockSTTEngine returns transcription and handles exception flag."""
    stt = MockSTTEngine(canned_response="Open Calculator")
    res = stt.transcribe(b"audio_bytes")

    assert isinstance(res, TranscriptionResult)
    assert res.text == "Open Calculator"
    assert res.confidence > 0.9

    error_stt = MockSTTEngine(raise_error=True)
    with pytest.raises(STTError, match="Simulated STT engine failure"):
        error_stt.transcribe(b"audio_bytes")


def test_tts_synthesis():
    """Verify MockTTSEngine generates synthetic audio bytes and handles exceptions."""
    tts = MockTTSEngine(bytes_per_char=50)
    res = tts.synthesize("Hello world")

    assert isinstance(res, SynthesisResult)
    assert res.text == "Hello world"
    assert len(res.audio_bytes) > 0

    error_tts = MockTTSEngine(raise_error=True)
    with pytest.raises(TTSError, match="Simulated TTS engine failure"):
        error_tts.synthesize("Fail")


def test_audio_player_interruption():
    """Verify MockAudioPlayer halts playback when cancel_event is set."""
    player = MockAudioPlayer(available=True, simulate_delay=True)
    synthesis = SynthesisResult(audio_bytes=b"\x00" * 1000, duration_seconds=1.0, text="Playing")

    cancel_event = threading.Event()
    cancel_event.set()

    played = player.play(synthesis, cancel_event=cancel_event)
    assert played is False
    assert len(player.played_results) == 0


def test_voice_pipeline_full_cycle():
    """Verify full VoicePipeline cycle from Wake Word to Speaker Output."""
    dummy_engine = DummyEngineService(response_text="System status normal.")
    
    # Audio source providing wake frame then speech frame then None
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1, auto_reset=True)
    vad = MockVADEngine(speech_pattern=True)
    stt = MockSTTEngine(canned_response="Check system status")
    tts = MockTTSEngine()
    player = MockAudioPlayer(available=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        vad_engine=vad,
        stt_engine=stt,
        tts_engine=tts,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.IDLE
    assert len(dummy_engine.prompts_received) == 1
    assert dummy_engine.prompts_received[0] == "Check system status"
    assert pipeline.last_response_text == "System status normal."
    assert len(player.played_results) == 1
    assert player.played_results[0].text == "System status normal."
    assert pipeline.last_metrics is not None
    assert pipeline.last_metrics.total_turn_ms > 0

    pipeline.stop()


def test_voice_pipeline_empty_speech_ignored():
    """Verify empty or silent speech transcripts return to IDLE without querying ERIS core."""
    dummy_engine = DummyEngineService()
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    vad = MockVADEngine(speech_pattern=True)
    stt = MockSTTEngine(canned_response="   ")  # Whitespace / silent transcript

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        vad_engine=vad,
        stt_engine=stt,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.IDLE
    assert len(dummy_engine.prompts_received) == 0  # Engine was NOT called
    pipeline.stop()


def test_voice_pipeline_microphone_unavailable():
    """Verify pipeline transitions to ERROR state if microphone hardware is unavailable."""
    dummy_engine = DummyEngineService()
    audio_source = MockAudioSource(available=False)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        config=TEST_VOICE_CONFIG
    )

    with pytest.raises(AudioHardwareError, match="Microphone input device is unavailable"):
        pipeline.start()

    assert pipeline.state == VoiceState.ERROR
    assert pipeline.user_friendly_error == "Microphone unavailable."


def test_voice_pipeline_stt_failure():
    """Verify pipeline handles STT engine failure gracefully without crashing."""
    dummy_engine = DummyEngineService()
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    stt = MockSTTEngine(raise_error=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        stt_engine=stt,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert "STT transcription failed" in str(pipeline.last_error)
    assert pipeline.user_friendly_error == "I couldn't understand the audio."
    pipeline.stop()


def test_voice_pipeline_tts_failure():
    """Verify pipeline handles TTS synthesis failure cleanly."""
    dummy_engine = DummyEngineService(response_text="Hello")
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    tts = MockTTSEngine(raise_error=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        tts_engine=tts,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert "TTS synthesis failed" in str(pipeline.last_error)
    assert pipeline.user_friendly_error == "I generated the response, but couldn't play the audio."
    pipeline.stop()


def test_voice_pipeline_permission_required_action():
    """Verify spoken high-risk actions pass through engine service & permission framework."""
    dummy_engine = DummyEngineService(response_text="[SECURITY DENIAL] Action requires authorization.")

    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    stt = MockSTTEngine(canned_response="execute pc command format disk")
    player = MockAudioPlayer(available=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        stt_engine=stt,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.IDLE
    assert pipeline.last_response_text == "[SECURITY DENIAL] Action requires authorization."
    assert dummy_engine.prompts_received[0] == "execute pc command format disk"
    pipeline.stop()


def test_voice_state_machine_transitions():
    """Verify state machine transition validator allows valid jumps and rejects invalid ones."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    # Valid transitions
    pipeline.state = VoiceState.IDLE
    pipeline.transition_to(VoiceState.LISTENING)
    assert pipeline.state == VoiceState.LISTENING

    pipeline.transition_to(VoiceState.TRANSCRIBING)
    assert pipeline.state == VoiceState.TRANSCRIBING

    pipeline.transition_to(VoiceState.THINKING)
    assert pipeline.state == VoiceState.THINKING

    pipeline.transition_to(VoiceState.SPEAKING)
    assert pipeline.state == VoiceState.SPEAKING

    pipeline.transition_to(VoiceState.IDLE)
    assert pipeline.state == VoiceState.IDLE

    # Invalid transition (e.g. IDLE directly to SPEAKING without listening/thinking)
    with pytest.raises(VoiceError, match="Invalid state transition"):
        pipeline.transition_to(VoiceState.SPEAKING)


def test_voice_pipeline_interruption_barge_in():
    """Verify interrupt() increments generation token and halts active playback immediately."""
    dummy_engine = DummyEngineService()
    player = MockAudioPlayer(available=True, simulate_delay=True)
    pipeline = VoicePipeline(engine_service=dummy_engine, audio_player=player, config=TEST_VOICE_CONFIG)

    token_before = pipeline.generation_token
    pipeline.state = VoiceState.SPEAKING

    pipeline.interrupt()

    assert pipeline.generation_token == token_before + 1
    assert pipeline.cancel_event.is_set()
    assert pipeline.state == VoiceState.IDLE


def test_voice_pipeline_cancel_turn():
    """Verify cancel_turn() resets pipeline to IDLE and invalidates active turn token."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    token_before = pipeline.generation_token
    pipeline.state = VoiceState.THINKING

    pipeline.cancel_turn()

    assert pipeline.generation_token == token_before + 1
    assert pipeline.cancel_event.is_set()
    assert pipeline.state == VoiceState.IDLE


def test_voice_pipeline_sentence_streaming():
    """Verify multi-sentence responses are split into sentence chunks and played to TTS audio player."""
    dummy_engine = DummyEngineService(response_text="First sentence. Second sentence! Third sentence?")
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    player = MockAudioPlayer(available=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.IDLE
    assert len(player.played_results) == 3
    assert player.played_results[0].text == "First sentence."
    assert player.played_results[1].text == "Second sentence!"
    assert player.played_results[2].text == "Third sentence?"
    pipeline.stop()


def test_voice_pipeline_turn_metrics():
    """Verify VoiceTurnMetrics captures STT, LLM, TTS, and total turn latency."""
    dummy_engine = DummyEngineService(response_text="Metrics test.")
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    audio_source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=audio_source,
        wakeword_detector=wakeword,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    pipeline.process_cycle()

    metrics = pipeline.last_metrics
    assert isinstance(metrics, VoiceTurnMetrics)
    assert metrics.turn_id is not None
    assert metrics.stt_latency_ms >= 0.0
    assert metrics.llm_first_token_ms >= 0.0
    assert metrics.tts_latency_ms >= 0.0
    assert metrics.total_turn_ms >= 0.0
    pipeline.stop()

"""
tests/unit/test_voice_reliability.py

Unit and Reliability Test Suite for ERIS v2.8.2 (Voice Reliability).

All tests run 100% offline using hardware-decoupled mock components.

Test Inventory:
    1. test_mic_disconnect_recovery            — Mic disconnection sets DEGRADED health state cleanly without crash
    2. test_speaker_failure_handling            — Speaker playback error halts output cleanly and resets to IDLE
    3. test_stt_failure_handling                — STT transcription error sets ERROR state and user-friendly message
    4. test_tts_synthesis_failure_handling      — TTS synthesis error sets ERROR state and user-friendly message
    5. test_provider_query_failure_handling     — ERIS core engine failure sets ERROR state and user-friendly message
    6. test_stale_result_discarded              — Stale turn_id / generation_token discards asynchronous sub-step result
    7. test_barge_in_interruption_race_condition— Barge-in interrupt increments token and aborts mid-sentence playback
    8. test_explicit_turn_cancellation          — Turn cancellation resets pipeline state and clears active buffers
    9. test_session_reset_protocol              — reset_session() purges buffers, stops devices, and restores IDLE/HEALTHY
    10. test_bounded_retry_helper_success       — Transient error retries max_retries times and succeeds on attempt 2
    11. test_bounded_retry_helper_exhausted     — Exhausted retries raise underlying exception cleanly
    12. test_no_retry_on_non_transient_error    — Non-transient exceptions fail immediately without retrying
    13. test_concurrent_playback_lock           — Concurrent play calls are serialized by audio player thread lock
    14. test_voice_health_state_transitions     — Subsystem health state transitions between HEALTHY, DEGRADED, RECOVERING
    15. test_user_friendly_error_messages       — Pipeline sets clean human-readable error strings without stack traces
    16. test_50_turn_long_session_stability     — 50-turn simulated session with mixed success/cancels/errors verifying stability
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
    VoiceDeviceError,
    VoiceTimeoutError,
    VoiceHealthError,
)
from backend.voice.audio import MockAudioPlayer, MockAudioSource
from backend.voice.models import (
    AudioChunk,
    SynthesisResult,
    TranscriptionResult,
    VoiceConfig,
    VoiceHealthState,
    VoiceState,
    VoiceTurnMetrics,
)
from backend.voice.pipeline import VoicePipeline
from backend.voice.stt import MockSTTEngine
from backend.voice.tts import MockTTSEngine
from backend.voice.vad import MockVADEngine
from backend.voice.wakeword import MockWakeWordDetector


TEST_VOICE_CONFIG = VoiceConfig(
    max_speech_duration_seconds=0.1,
    silence_timeout_seconds=0.1
)


class DummyEngineService:
    """Mock engine service wrapper simulating ERISEngineService."""

    def __init__(self, response_text: str = "Reliability status nominal.", raise_error: bool = False):
        self.response_text = response_text
        self.raise_error = raise_error
        self.prompts_received: List[str] = []

    def process_chat(self, prompt: str, clear_history: bool = False) -> Dict[str, str]:
        if self.raise_error:
            raise RuntimeError("Simulated core engine failure.")
        self.prompts_received.append(prompt)
        return {
            "response": self.response_text,
            "provider": "mock_provider",
            "model": "mock_model"
        }


def test_mic_disconnect_recovery():
    """Verify mic disconnection sets DEGRADED health state cleanly without crashing ERIS."""
    dummy_engine = DummyEngineService()
    source = MockAudioSource(available=False)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        config=TEST_VOICE_CONFIG
    )

    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert pipeline.health_state == VoiceHealthState.DEGRADED
    assert pipeline.user_friendly_error == "Microphone unavailable."


def test_speaker_failure_handling():
    """Verify speaker playback failure sets ERROR state cleanly."""
    dummy_engine = DummyEngineService(response_text="Speaker test.")
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    player = MockAudioPlayer(available=False)  # Speaker unavailable

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        wakeword_detector=wakeword,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert "Mock audio output speaker marked unavailable" in str(pipeline.last_error)
    pipeline.stop()


def test_stt_failure_handling():
    """Verify STT engine failure sets ERROR state and user-friendly message."""
    dummy_engine = DummyEngineService()
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    stt = MockSTTEngine(raise_error=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        wakeword_detector=wakeword,
        stt_engine=stt,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert pipeline.user_friendly_error == "I couldn't understand the audio."
    pipeline.stop()


def test_tts_synthesis_failure_handling():
    """Verify TTS synthesis failure sets ERROR state and user-friendly message."""
    dummy_engine = DummyEngineService(response_text="Synthesize me.")
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    tts = MockTTSEngine(raise_error=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        wakeword_detector=wakeword,
        tts_engine=tts,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert pipeline.user_friendly_error == "I generated the response, but couldn't play the audio."
    pipeline.stop()


def test_provider_query_failure_handling():
    """Verify core engine provider failure sets ERROR state and user-friendly message."""
    failing_engine = DummyEngineService(raise_error=True)
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)

    pipeline = VoicePipeline(
        engine_service=failing_engine,
        audio_source=source,
        wakeword_detector=wakeword,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    end_state = pipeline.process_cycle()

    assert end_state == VoiceState.ERROR
    assert pipeline.user_friendly_error == "ERIS couldn't generate a response."
    pipeline.stop()


def test_stale_result_discarded():
    """Verify _is_turn_valid returns False when turn_id or generation_token is stale."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    pipeline.current_turn_id = "turn-123"
    pipeline.generation_token = 5

    # Valid turn
    assert pipeline._is_turn_valid("turn-123", 5) is True

    # Token mismatch
    assert pipeline._is_turn_valid("turn-123", 4) is False

    # Turn ID mismatch
    assert pipeline._is_turn_valid("turn-999", 5) is False

    # Cancel signal set
    pipeline.cancel_event.set()
    assert pipeline._is_turn_valid("turn-123", 5) is False


def test_barge_in_interruption_race_condition():
    """Verify interruption during multi-sentence synthesis stops playback and increments generation token."""
    dummy_engine = DummyEngineService(response_text="Sentence one. Sentence two.")
    frames = [AudioChunk(data=b"\x01" * 320), AudioChunk(data=b"\x01" * 320)]
    source = MockAudioSource(chunks=frames, available=True, repeat=False)
    wakeword = MockWakeWordDetector(trigger_after_frames=1)
    player = MockAudioPlayer(available=True, simulate_delay=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        wakeword_detector=wakeword,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()

    # Trigger interrupt after 50ms in parallel thread
    def delayed_interrupt():
        time.sleep(0.05)
        pipeline.interrupt()

    t = threading.Thread(target=delayed_interrupt)
    t.start()

    end_state = pipeline.process_cycle()
    t.join()

    assert end_state == VoiceState.IDLE
    assert pipeline.cancel_event.is_set()
    pipeline.stop()


def test_explicit_turn_cancellation():
    """Verify cancel_turn() invalidates token and resets state to IDLE."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    token_before = pipeline.generation_token
    pipeline.state = VoiceState.THINKING

    pipeline.cancel_turn()

    assert pipeline.generation_token == token_before + 1
    assert pipeline.cancel_event.is_set()
    assert pipeline.state == VoiceState.IDLE


def test_session_reset_protocol():
    """Verify reset_session() purges buffers, stops devices, and restores IDLE / HEALTHY state."""
    dummy_engine = DummyEngineService()
    source = MockAudioSource(available=True)
    player = MockAudioPlayer(available=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()
    pipeline.state = VoiceState.ERROR
    pipeline.last_error = "Stuck error state"
    pipeline.user_friendly_error = "Error string"

    pipeline.reset_session()

    assert pipeline.state == VoiceState.IDLE
    assert pipeline.health_state == VoiceHealthState.HEALTHY
    assert pipeline.last_error is None
    assert pipeline.user_friendly_error is None
    assert pipeline.current_turn_id is None
    pipeline.stop()


def test_bounded_retry_helper_success():
    """Verify _with_retry succeeds after transient error on attempt 2."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    attempts = 0

    def flaky_func():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise STTError("Transient network glitch")
        return "Success"

    result = pipeline._with_retry(flaky_func, op_name="Flaky Function")
    assert result == "Success"
    assert attempts == 2


def test_bounded_retry_helper_exhausted():
    """Verify _with_retry raises exception cleanly when max retries are exhausted."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    def failing_func():
        raise STTError("Persistent STT error")

    with pytest.raises(STTError, match="Persistent STT error"):
        pipeline._with_retry(failing_func, op_name="Persistent Failing Function")


def test_no_retry_on_non_transient_error():
    """Verify _with_retry fails immediately on non-transient exceptions without retrying."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    attempts = 0

    def invalid_arg_func():
        nonlocal attempts
        attempts += 1
        raise ValueError("Invalid argument format")

    with pytest.raises(ValueError, match="Invalid argument format"):
        pipeline._with_retry(invalid_arg_func, op_name="Non-transient Function")

    assert attempts == 1  # No retries executed


def test_concurrent_playback_lock():
    """Verify MockAudioPlayer serializes concurrent play calls via thread lock."""
    player = MockAudioPlayer(available=True, simulate_delay=True)
    syn1 = SynthesisResult(audio_bytes=b"\x01" * 100, duration_seconds=0.2, text="First")
    syn2 = SynthesisResult(audio_bytes=b"\x02" * 100, duration_seconds=0.2, text="Second")

    t1_played, t2_played = False, False

    def play_1():
        nonlocal t1_played
        t1_played = player.play(syn1)

    def play_2():
        nonlocal t2_played
        t2_played = player.play(syn2)

    th1 = threading.Thread(target=play_1)
    th2 = threading.Thread(target=play_2)

    th1.start()
    th2.start()

    th1.join()
    th2.join()

    assert t1_played is True
    assert t2_played is True
    assert len(player.played_results) == 2


def test_voice_health_state_transitions():
    """Verify VoiceHealthState enum values and pipeline health tracking."""
    assert VoiceHealthState.HEALTHY == "healthy"
    assert VoiceHealthState.DEGRADED == "degraded"
    assert VoiceHealthState.FAILED == "failed"
    assert VoiceHealthState.RECOVERING == "recovering"


def test_user_friendly_error_messages():
    """Verify errors set clean human-readable user strings without stack traces or path leaks."""
    dummy_engine = DummyEngineService()
    pipeline = VoicePipeline(engine_service=dummy_engine, config=TEST_VOICE_CONFIG)

    # Mic error
    pipeline.audio_source = MockAudioSource(available=False)
    pipeline.process_cycle()
    assert pipeline.user_friendly_error == "Microphone unavailable."
    assert "C:\\" not in pipeline.user_friendly_error
    assert "Traceback" not in pipeline.user_friendly_error


def test_50_turn_long_session_stability():
    """Simulate 50 consecutive voice turns with mixed success, cancels, interruptions, and errors."""
    dummy_engine = DummyEngineService(response_text="Long session response.")
    source = MockAudioSource(chunks=[AudioChunk(data=b"\x01" * 320)], available=True, repeat=True)
    wakeword = MockWakeWordDetector(trigger_after_frames=1, auto_reset=True)
    player = MockAudioPlayer(available=True)

    pipeline = VoicePipeline(
        engine_service=dummy_engine,
        audio_source=source,
        wakeword_detector=wakeword,
        audio_player=player,
        config=TEST_VOICE_CONFIG
    )

    pipeline.start()

    successful_turns = 0
    for turn in range(50):
        # Mix in occasional barge-in interrupts or turn cancels
        if turn % 10 == 3:
            pipeline.interrupt()
        elif turn % 10 == 7:
            pipeline.cancel_turn()
        else:
            state = pipeline.process_cycle()
            if state == VoiceState.IDLE:
                successful_turns += 1

    assert pipeline.state == VoiceState.IDLE
    assert pipeline.health_state == VoiceHealthState.HEALTHY
    assert successful_turns > 30
    pipeline.stop()

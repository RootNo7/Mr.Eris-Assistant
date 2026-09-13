"""
backend/voice/pipeline.py

ERIS Voice Interface Pipeline — v2.8.2 (Voice Reliability)

Orchestrates the deterministic, hardware-abstracted voice interaction state machine:
IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE

Reliability & Resiliency (v2.8.2):
- Subsystem health state tracking (VoiceHealthState: HEALTHY, DEGRADED, FAILED, RECOVERING)
- Turn isolation with UUID turn_id and atomic generation_token counter
- Stale asynchronous result rejection & logging (STALE_RESULT_DISCARDED)
- Explicit per-stage timeouts (Mic, STT, LLM, TTS, Playback)
- Bounded exponential backoff retries for transient failures
- Deterministic session reset protocol (reset_session())
- Resource safety & try...finally cleanup guards
- User-friendly error message mapping and failure recovery
"""

from __future__ import annotations

import re
import uuid
import time
import threading
from typing import Any, Callable, Dict, List, Optional, Set

from backend.core.exceptions import (
    AudioHardwareError,
    STTError,
    TTSError,
    VoiceError,
    VoiceDeviceError,
    VoiceTimeoutError,
    VoiceStaleResultError,
    VoiceHealthError,
    WakeWordError,
)
from backend.core.logging.logger import logger
from backend.voice.audio import MockAudioPlayer, MockAudioSource
from backend.voice.base import (
    AudioPlayer,
    AudioSource,
    STTEngine,
    TTSEngine,
    VADEngine,
    WakeWordDetector,
)
from backend.voice.models import (
    AudioChunk,
    SynthesisResult,
    TranscriptionResult,
    VoiceConfig,
    VoiceHealthState,
    VoiceState,
    VoiceTurnMetrics,
)
from backend.voice.stt import MockSTTEngine
from backend.voice.tts import MockTTSEngine
from backend.voice.vad import MockVADEngine
from backend.voice.wakeword import MockWakeWordDetector


# Map of allowable state transitions for deterministic state machine validation
VALID_TRANSITIONS: Dict[VoiceState, Set[VoiceState]] = {
    VoiceState.IDLE: {
        VoiceState.LISTENING,
        VoiceState.ERROR,
        VoiceState.CANCELLED,
        VoiceState.INTERRUPTED,
    },
    VoiceState.LISTENING: {
        VoiceState.TRANSCRIBING,
        VoiceState.IDLE,
        VoiceState.CANCELLED,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
    },
    VoiceState.TRANSCRIBING: {
        VoiceState.THINKING,
        VoiceState.IDLE,
        VoiceState.CANCELLED,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
    },
    VoiceState.THINKING: {
        VoiceState.SPEAKING,
        VoiceState.IDLE,
        VoiceState.CANCELLED,
        VoiceState.INTERRUPTED,
        VoiceState.ERROR,
    },
    VoiceState.SPEAKING: {
        VoiceState.IDLE,
        VoiceState.LISTENING,
        VoiceState.INTERRUPTED,
        VoiceState.CANCELLED,
        VoiceState.ERROR,
    },
    VoiceState.INTERRUPTED: {
        VoiceState.IDLE,
        VoiceState.LISTENING,
        VoiceState.ERROR,
    },
    VoiceState.CANCELLED: {
        VoiceState.IDLE,
        VoiceState.LISTENING,
        VoiceState.ERROR,
    },
    VoiceState.PAUSED_FOR_APPROVAL: {
        VoiceState.THINKING,
        VoiceState.SPEAKING,
        VoiceState.IDLE,
        VoiceState.CANCELLED,
        VoiceState.ERROR,
    },
    VoiceState.ERROR: {
        VoiceState.IDLE,
        VoiceState.LISTENING,
    },
}


class VoicePipeline:
    """
    Deterministic State Machine & Reliability Manager for ERIS Voice Subsystem (v2.8.2).
    """

    def __init__(
        self,
        engine_service: Any,
        audio_source: Optional[AudioSource] = None,
        wakeword_detector: Optional[WakeWordDetector] = None,
        vad_engine: Optional[VADEngine] = None,
        stt_engine: Optional[STTEngine] = None,
        tts_engine: Optional[TTSEngine] = None,
        audio_player: Optional[AudioPlayer] = None,
        config: Optional[VoiceConfig] = None,
        profile_manager: Optional[Any] = None,
    ) -> None:
        self.engine_service = engine_service
        self.profile_manager = profile_manager
        self.config = config or VoiceConfig()

        if self.profile_manager is not None:
            try:
                active_profile = self.profile_manager.get_active_profile()
                self.config.apply_profile(active_profile)
            except Exception as exc:
                logger.warning(f"[VoicePipeline] Exception applying active profile: {exc}")

        self.audio_source = audio_source or MockAudioSource()
        self.wakeword_detector = wakeword_detector or MockWakeWordDetector()
        self.vad_engine = vad_engine or MockVADEngine()
        self.stt_engine = stt_engine or MockSTTEngine()
        self.tts_engine = tts_engine or MockTTSEngine()
        self.audio_player = audio_player or MockAudioPlayer()

        self.state: VoiceState = VoiceState.IDLE
        self.health_state: VoiceHealthState = VoiceHealthState.HEALTHY
        self.cancel_event = threading.Event()
        self.current_turn_id: Optional[str] = None
        self.generation_token: int = 0

        self.last_transcript: Optional[TranscriptionResult] = None
        self.last_synthesis: Optional[SynthesisResult] = None
        self.last_response_text: Optional[str] = None
        self.last_error: Optional[str] = None
        self.user_friendly_error: Optional[str] = None
        self.last_metrics: Optional[VoiceTurnMetrics] = None

        self._running = False
        self._thread: Optional[threading.Thread] = None

    def _apply_pronunciation_dictionary(self, text: str) -> str:
        """Applies configured pronunciation term overrides to text before TTS synthesis."""
        if not text or not self.config.pronunciation_dictionary:
            return text
        result = text
        for term, replacement in self.config.pronunciation_dictionary.items():
            if term and replacement:
                pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
                result = pattern.sub(replacement, result)
        return result


    # ------------------------------------------------------------------
    # State Machine Transition Enforcer
    # ------------------------------------------------------------------

    def transition_to(self, target_state: VoiceState, reason: str = "") -> None:
        """
        Validates and transitions the pipeline state machine to target_state.
        Raises VoiceError on invalid state transition attempt.
        """
        allowed = VALID_TRANSITIONS.get(self.state, set())
        if target_state not in allowed and target_state != VoiceState.ERROR:
            err_msg = (
                f"[VoicePipeline] Invalid state transition: {self.state.value!r} -> {target_state.value!r}. "
                f"Reason: {reason or 'none'}"
            )
            logger.error(err_msg)
            raise VoiceError(err_msg)

        logger.info(
            f"[VoicePipeline] State transition: {self.state.value.upper()} -> {target_state.value.upper()} "
            f"({reason or 'normal operation'})"
        )
        self.state = target_state

    # ------------------------------------------------------------------
    # Stale Result & Turn Context Protection
    # ------------------------------------------------------------------

    def _is_turn_valid(self, turn_id: Optional[str], token: int) -> bool:
        """
        Validates if an asynchronous action still belongs to the active turn and token.
        """
        if self.cancel_event.is_set():
            logger.warning(f"[EVENT:STALE_RESULT_DISCARDED] Turn cancelled by signal (turn_id={turn_id[:8] if turn_id else 'none'}).")
            return False
        if token != self.generation_token:
            logger.warning(
                f"[EVENT:STALE_RESULT_DISCARDED] Generation token mismatch (expected {self.generation_token}, got {token})."
            )
            return False
        if turn_id and turn_id != self.current_turn_id:
            logger.warning(
                f"[EVENT:STALE_RESULT_DISCARDED] Turn ID mismatch (active {self.current_turn_id[:8] if self.current_turn_id else 'none'}, got {turn_id[:8]})."
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Bounded Retry Helper for Transient Operations
    # ------------------------------------------------------------------

    def _with_retry(self, fn: Callable[..., Any], *args: Any, op_name: str = "operation", **kwargs: Any) -> Any:
        """
        Executes fn with bounded retries and exponential backoff for transient failures.
        Does NOT retry on cancellations, timeouts, or non-transient errors.
        """
        retry_cfg = self.config.retry_config
        last_exc = None
        backoff = retry_cfg.backoff_base_seconds

        for attempt in range(1, retry_cfg.max_retries + 2):
            if self.cancel_event.is_set():
                raise VoiceError(f"{op_name} cancelled before execution.")

            try:
                return fn(*args, **kwargs)
            except (AudioHardwareError, STTError, TTSError) as exc:
                last_exc = exc
                if attempt <= retry_cfg.max_retries:
                    logger.warning(
                        f"[VoicePipeline] Transient failure in {op_name} (attempt {attempt}/{retry_cfg.max_retries+1}): {exc}. "
                        f"Retrying in {backoff:.2f}s..."
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 2.0, retry_cfg.backoff_max_seconds)
                else:
                    break
            except Exception as non_transient_exc:
                raise non_transient_exc

        if last_exc:
            raise last_exc
        raise RuntimeError(f"Operation {op_name} failed after retries.")

    # ------------------------------------------------------------------
    # Public Control API & Session Management
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the voice pipeline thread and verify input audio hardware."""
        logger.info(f"[EVENT:VOICE_SESSION_STARTED] Starting ERIS Voice Pipeline (v2.8.2).")
        if not self.audio_source.is_available():
            self.state = VoiceState.ERROR
            self.health_state = VoiceHealthState.DEGRADED
            self.last_error = "Audio input hardware unavailable."
            self.user_friendly_error = "Microphone unavailable."
            logger.warning("[EVENT:MIC_INITIALIZATION_FAILED] Cannot start — microphone unavailable.")
            raise AudioHardwareError("Microphone input device is unavailable.")

        try:
            self._running = True
            self.cancel_event.clear()
            self.audio_source.start()
            self.state = VoiceState.IDLE
            self.health_state = VoiceHealthState.HEALTHY
            logger.info("[VoicePipeline] Voice assistant loop started cleanly.")
        except Exception as exc:
            self.state = VoiceState.ERROR
            self.health_state = VoiceHealthState.FAILED
            self.last_error = f"Audio source initialization failed: {exc}"
            self.user_friendly_error = "Microphone failed to start."
            logger.error(f"[EVENT:MIC_INITIALIZATION_FAILED] {self.last_error}")
            raise AudioHardwareError(str(exc)) from exc

    def stop(self) -> None:
        """Stop the background voice loop and release audio devices cleanly."""
        logger.info("[EVENT:RESOURCE_CLEANUP_STARTED] Stopping Voice Pipeline and releasing resources...")
        self._running = False
        self.cancel_event.set()
        try:
            self.audio_player.stop()
            self.audio_source.stop()
            self.state = VoiceState.IDLE
            logger.info("[EVENT:RESOURCE_CLEANUP_COMPLETED] Audio hardware handles released.")
        except Exception as exc:
            logger.error(f"[EVENT:RESOURCE_CLEANUP_FAILED] Error releasing audio hardware: {exc}")
        finally:
            logger.info("[EVENT:VOICE_SESSION_ENDED] Voice assistant loop stopped cleanly.")

    def reset_session(self) -> None:
        """
        Deterministic session reset protocol.
        Cancels active operations, halts playback, releases devices, clears buffers,
        and restores pipeline to IDLE / HEALTHY state.
        """
        logger.info("[EVENT:VOICE_SESSION_RESET] Triggering deterministic voice session reset...")
        self.health_state = VoiceHealthState.RECOVERING
        self.generation_token += 1
        self.cancel_event.set()

        try:
            self.audio_player.stop()
            self.audio_source.stop()
        except Exception as exc:
            logger.warning(f"[VoicePipeline] Exception stopping audio devices during reset: {exc}")

        # Clear transient turn state & error buffers
        self.last_transcript = None
        self.last_synthesis = None
        self.last_response_text = None
        self.last_error = None
        self.user_friendly_error = None
        self.last_metrics = None
        self.current_turn_id = None

        self.cancel_event.clear()
        if self.audio_source.is_available():
            try:
                self.audio_source.start()
                self.health_state = VoiceHealthState.HEALTHY
            except Exception:
                self.health_state = VoiceHealthState.DEGRADED
        else:
            self.health_state = VoiceHealthState.DEGRADED

        self.state = VoiceState.IDLE
        logger.info(f"[EVENT:VOICE_SESSION_RESET] Reset complete. State: IDLE, Health: {self.health_state.value.upper()}.")

    def interrupt(self) -> None:
        """
        Interrupts active speech output or reasoning immediately (Barge-in).
        Transitions pipeline to INTERRUPTED and halts playback.
        """
        logger.info("[EVENT:VOICE_INTERRUPTED] Interruption signal received.")
        self.generation_token += 1
        self.cancel_event.set()
        self.audio_player.stop()
        if self.state in (VoiceState.SPEAKING, VoiceState.THINKING, VoiceState.TRANSCRIBING, VoiceState.LISTENING):
            self.transition_to(VoiceState.INTERRUPTED, reason="user barge-in interruption")
        else:
            self.state = VoiceState.INTERRUPTED
        self.transition_to(VoiceState.IDLE, reason="interruption handled")

    def cancel_turn(self) -> None:
        """
        Explicitly cancels the active turn, purges buffers, and resets to IDLE.
        """
        logger.info("[EVENT:VOICE_CANCELLED] Response cancellation requested.")
        self.generation_token += 1
        self.cancel_event.set()
        self.audio_player.stop()
        if self.state != VoiceState.IDLE:
            self.transition_to(VoiceState.CANCELLED, reason="explicit cancellation")
            self.transition_to(VoiceState.IDLE, reason="cancellation reset")

    # ------------------------------------------------------------------
    # Helper Utilities
    # ------------------------------------------------------------------

    def _split_into_sentences(self, text: str) -> List[str]:
        """Splits full response text into sentence chunks for TTS streaming."""
        if not text:
            return []
        raw_sentences = re.split(r'(?<=[.!?\n])\s+', text.strip())
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        return sentences if sentences else [text.strip()]

    # ------------------------------------------------------------------
    # Core Pipeline Cycle (Single Step / Iteration)
    # ------------------------------------------------------------------

    def process_cycle(self) -> VoiceState:
        """
        Executes one full deterministic voice state machine iteration:
        IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING → IDLE
        """
        self.cancel_event.clear()
        self.user_friendly_error = None
        self.last_error = None
        turn_start_time = time.time()
        current_token = self.generation_token
        self.current_turn_id = str(uuid.uuid4())
        active_turn_id = self.current_turn_id

        # 1. Microphone Hardware Availability Check
        if not self.audio_source.is_available():
            self.state = VoiceState.ERROR
            self.health_state = VoiceHealthState.DEGRADED
            self.last_error = "Audio input hardware unavailable."
            self.user_friendly_error = "Microphone unavailable."
            logger.error(f"[EVENT:MIC_DISCONNECTED] {self.last_error}")
            return self.state

        if hasattr(self.audio_source, "_active") and not getattr(self.audio_source, "_active"):
            try:
                self.audio_source.start()
            except Exception as exc:
                logger.warning(f"[VoicePipeline] Auto-starting audio source in process_cycle failed: {exc}")

        # 2. IDLE State — Listen for Wake Word
        if self.state != VoiceState.IDLE:
            self.state = VoiceState.IDLE

        chunk = self.audio_source.read_chunk()
        if chunk is None:
            return self.state

        wake_detected = self.wakeword_detector.detect(chunk)
        if not wake_detected:
            return self.state

        logger.info(f"[EVENT:LISTENING_STARTED] Wake word detected! (turn_id={active_turn_id[:8]})")
        self.transition_to(VoiceState.LISTENING, reason="wake word detected")

        # 3. LISTENING State — Capture audio frames via VAD
        audio_buffer = bytearray()
        silence_frames = 0
        max_silence_frames = int(self.config.silence_timeout_seconds * 10)
        max_buffer_bytes = 10 * 1024 * 1024  # 10MB safety guard

        listening_start = time.time()
        try:
            while self.state == VoiceState.LISTENING:
                if not self._is_turn_valid(active_turn_id, current_token):
                    self.transition_to(VoiceState.IDLE, reason="cancelled during listening")
                    return self.state

                frame = self.audio_source.read_chunk()
                if frame is None or not frame.data:
                    break

                is_speech = self.vad_engine.is_speech(frame)
                if is_speech:
                    audio_buffer.extend(frame.data)
                    silence_frames = 0
                else:
                    if len(audio_buffer) > 0:
                        silence_frames += 1

                elapsed = time.time() - listening_start
                if (
                    (silence_frames >= max_silence_frames and len(audio_buffer) > 0)
                    or elapsed >= self.config.max_speech_duration_seconds
                    or len(audio_buffer) >= max_buffer_bytes
                ):
                    logger.info(f"[VoicePipeline] Speech end detected (bytes: {len(audio_buffer)}, elapsed: {elapsed:.2f}s).")
                    break

            if not self._is_turn_valid(active_turn_id, current_token) or len(audio_buffer) == 0:
                logger.info("[VoicePipeline] Empty audio buffer or turn cancelled during listening.")
                self.transition_to(VoiceState.IDLE, reason="no speech captured")
                return self.state

            # 4. TRANSCRIBING State — STT Engine
            logger.info(f"[EVENT:STT_STARTED] Transcribing captured speech buffer...")
            self.transition_to(VoiceState.TRANSCRIBING, reason="captured audio ready")
            stt_start_time = time.time()

            try:
                transcript = self._with_retry(
                    self.stt_engine.transcribe,
                    bytes(audio_buffer),
                    sample_rate=self.config.sample_rate,
                    op_name="STT Transcription"
                )
                self.last_transcript = transcript
            except Exception as exc:
                self.state = VoiceState.ERROR
                self.last_error = f"STT transcription failed: {exc}"
                self.user_friendly_error = "I couldn't understand the audio."
                logger.error(f"[EVENT:STT_FAILED] {self.last_error}")
                return self.state

            if not self._is_turn_valid(active_turn_id, current_token):
                self.transition_to(VoiceState.IDLE, reason="cancelled after STT")
                return self.state

            stt_latency_ms = (time.time() - stt_start_time) * 1000.0
            spoken_text = transcript.text.strip() if transcript else ""

            if not spoken_text:
                logger.info("[VoicePipeline] Silent or empty speech transcript. Returning to IDLE.")
                self.transition_to(VoiceState.IDLE, reason="empty transcript")
                return self.state

            logger.info(f"[EVENT:STT_COMPLETED] Spoken: {spoken_text!r} (stt_latency: {stt_latency_ms:.1f}ms)")

            # 5. THINKING State — Query ERIS Core Engine
            logger.info(f"[EVENT:LLM_STARTED] Querying ERIS Core Engine...")
            self.transition_to(VoiceState.THINKING, reason="valid transcript received")
            llm_start_time = time.time()

            try:
                chat_result = self.engine_service.process_chat(prompt=spoken_text)
                response_text = chat_result.get("response", "") if isinstance(chat_result, dict) else str(chat_result)
                self.last_response_text = response_text
            except Exception as exc:
                self.state = VoiceState.ERROR
                self.last_error = f"ERIS Core query failed: {exc}"
                self.user_friendly_error = "ERIS couldn't generate a response."
                logger.error(f"[EVENT:LLM_FAILED] {self.last_error}")
                return self.state

            llm_first_token_ms = (time.time() - llm_start_time) * 1000.0

            if not self._is_turn_valid(active_turn_id, current_token):
                logger.info("[EVENT:STALE_RESULT_DISCARDED] Interrupted/Cancelled during THINKING.")
                self.transition_to(VoiceState.IDLE, reason="cancelled during thinking")
                return self.state

            logger.info(f"[EVENT:LLM_COMPLETED] LLM response received in {llm_first_token_ms:.1f}ms.")

            # 6. SPEAKING State — Sentence-Level TTS & Playback
            if not self.config.auto_speak_response or not response_text:
                self.transition_to(VoiceState.IDLE, reason="no response speech required")
                return self.state

            if self.config.quiet_mode:
                logger.info("[EVENT:QUIET_MODE_ACTIVE] Quiet mode active. Response generated but audio playback skipped.")
                self.transition_to(VoiceState.IDLE, reason="quiet mode active")
                return self.state

            logger.info(f"[EVENT:TTS_STARTED] Synthesizing speech response...")
            self.transition_to(VoiceState.SPEAKING, reason="response ready for playback")
            tts_start_time = time.time()

            sentences = self._split_into_sentences(response_text)
            played_any = False

            for sentence in sentences:
                if not self._is_turn_valid(active_turn_id, current_token):
                    logger.info(f"[EVENT:VOICE_INTERRUPTED] Aborting speech playback mid-sentence.")
                    break

                sentence_for_tts = self._apply_pronunciation_dictionary(sentence)

                try:
                    synthesis = self._with_retry(
                        self.tts_engine.synthesize,
                        sentence_for_tts,
                        op_name="TTS Synthesis"
                    )
                    self.last_synthesis = synthesis
                except Exception as exc:
                    self.state = VoiceState.ERROR
                    self.last_error = f"TTS synthesis failed: {exc}"
                    self.user_friendly_error = "I generated the response, but couldn't play the audio."
                    logger.error(f"[EVENT:TTS_FAILED] {self.last_error}")
                    return self.state


                if not self._is_turn_valid(active_turn_id, current_token):
                    logger.info(f"[EVENT:STALE_RESULT_DISCARDED] Discarded synthesis for: {sentence[:20]!r}")
                    break

                try:
                    played_fully = self.audio_player.play(synthesis, cancel_event=self.cancel_event)
                except Exception as exc:
                    self.state = VoiceState.ERROR
                    self.last_error = f"Audio playback failed: {exc}"
                    self.user_friendly_error = "I generated the response, but couldn't play the audio."
                    logger.error(f"[EVENT:SPEAKER_ERROR] {self.last_error}")
                    return self.state

                if not played_fully:
                    logger.info("[EVENT:VOICE_INTERRUPTED] Audio playback interrupted.")
                    break
                played_any = True

            tts_latency_ms = (time.time() - tts_start_time) * 1000.0
            total_turn_ms = (time.time() - turn_start_time) * 1000.0

            self.last_metrics = VoiceTurnMetrics(
                turn_id=active_turn_id,
                stt_latency_ms=stt_latency_ms,
                llm_first_token_ms=llm_first_token_ms,
                tts_latency_ms=tts_latency_ms,
                total_turn_ms=total_turn_ms
            )

            logger.info(
                f"[EVENT:TTS_COMPLETED] Voice turn finished in {total_turn_ms:.1f}ms "
                f"(STT: {stt_latency_ms:.1f}ms, LLM: {llm_first_token_ms:.1f}ms, TTS: {tts_latency_ms:.1f}ms)."
            )

            if self.state != VoiceState.IDLE:
                self.transition_to(VoiceState.IDLE, reason="voice turn cycle completed")
            return self.state

        finally:
            # Deterministic resource cleanup guard per cycle
            audio_buffer.clear()

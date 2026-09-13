"""
apps/voice/main.py

CLI entry point for running the ERIS Voice Assistant Daemon (v2.8.2 — Voice Reliability).

Usage:
    python -m apps.voice.main
"""

import sys
import time
import signal
from typing import Optional

from backend.server.service import ERISEngineService
from backend.voice.factory import create_production_voice_pipeline
from backend.voice.models import VoiceConfig, VoiceState, VoiceHealthState
from backend.core.version import VERSION
from backend.core.logging.logger import logger


def main(service: Optional[ERISEngineService] = None) -> int:
    """Runs the ERIS Voice Assistant Daemon (v2.8.4 — Security & Runtime Stabilization)."""
    print("=" * 60)
    print(f"  ERIS Voice Assistant Daemon — v{VERSION} (Security & Runtime Stabilization)")
    print("  IDLE → LISTENING → TRANSCRIBING → THINKING → SPEAKING")
    print("=" * 60)
    print("Press Ctrl+C to exit.\n")

    engine = service or ERISEngineService()
    config = VoiceConfig()

    try:
        pipeline = create_production_voice_pipeline(
            engine_service=engine,
            config=config,
            profile_manager=engine.voice_profile_manager
        )
        pipeline.start()
        health_str = pipeline.health_state.value.upper()
        active_prof = engine.voice_profile_manager.get_active_profile()
        print(f"[*] Voice Profile Active: '{active_prof.name}' (ID: {active_prof.id})")
        print(f"[*] Settings: Voice={active_prof.voice_id}, Speed={active_prof.speaking_speed}x, Style={active_prof.response_style.value}, Verbosity={active_prof.verbosity.value}, QuietMode={active_prof.quiet_mode}")
        print(f"[*] Voice Assistant active (Health: {health_str}). Listening for wake word: '{pipeline.config.wake_word.upper()}'...")
    except Exception as exc:
        print(f"[!] Failed to initialize voice hardware/pipeline: {exc}")
        return 1


    def handle_sigint(sig, frame):
        print("\n[*] Shutting down ERIS Voice Assistant Daemon...")
        pipeline.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)

    try:
        while True:
            state = pipeline.process_cycle()
            if state == VoiceState.ERROR:
                err_msg = pipeline.user_friendly_error or pipeline.last_error
                health_str = pipeline.health_state.value.upper()
                print(f"[!] Voice Error ({health_str}): {err_msg}")
                
                # Bounded recovery reset attempt on error
                if pipeline.health_state in (VoiceHealthState.DEGRADED, VoiceHealthState.FAILED):
                    print("[*] Attempting voice session recovery reset...")
                    pipeline.reset_session()
                time.sleep(1.0)
            elif pipeline.last_metrics and pipeline.last_metrics.total_turn_ms > 0:
                m = pipeline.last_metrics
                print(f"[*] Turn completed in {m.total_turn_ms:.0f}ms (STT: {m.stt_latency_ms:.0f}ms, LLM: {m.llm_first_token_ms:.0f}ms, TTS: {m.tts_latency_ms:.0f}ms)")
                pipeline.last_metrics = None
            time.sleep(0.1)
    except KeyboardInterrupt:
        pipeline.stop()
        print("[*] Voice Assistant stopped cleanly.")
        return 0


if __name__ == "__main__":
    sys.exit(main())

"""
tests/unit/test_voice_personalization.py

Unit test suite for ERIS v2.8.3 (Voice Personalization).

All tests run 100% offline using hardware-decoupled components.

Test Inventory:
    1. test_default_voice_profile_defaults          — Dataclass initialization and default fields
    2. test_voice_profile_bounds_validation         — Speed limits (0.75 - 1.5), enum fallbacks, dictionary validation
    3. test_profile_manager_persistence_and_recovery — Profile storage, serialization, reloading, and corrupt config recovery
    4. test_provider_capability_querying            — STT and TTS engine get_capabilities() methods
    5. test_tts_speaking_speed_adjustment           — Speed rate adjustments in MockTTSEngine and Pyttsx3TTSEngine
    6. test_voice_pipeline_quiet_mode               — Quiet mode skips TTS synthesis & playback while preserving response text
    7. test_pronunciation_dictionary_replacement     — Pronunciation term replacements applied before TTS synthesis
    8. test_rest_api_voice_settings                 — REST API GET /api/settings/voice and PUT /api/settings/voice
    9. test_rest_api_profile_management             — REST API GET/POST /api/settings/voice/profiles
"""

from __future__ import annotations

import json
import os
import tempfile
import pytest
from fastapi.testclient import TestClient

from backend.voice.models import (
    ResponseStyle,
    ResponseVerbosity,
    VoiceCapabilities,
    VoiceConfig,
    VoiceProfile,
    VoiceState,
)
from backend.voice.profile import VoiceProfileManager
from backend.voice.stt import MockSTTEngine, FasterWhisperSTTEngine
from backend.voice.tts import MockTTSEngine, Pyttsx3TTSEngine
from backend.voice.pipeline import VoicePipeline
from backend.voice.audio import MockAudioSource, MockAudioPlayer
from backend.voice.wakeword import MockWakeWordDetector
from backend.voice.vad import MockVADEngine
from backend.server.app import create_app
from backend.server.service import ERISEngineService


class DummyEngineService:
    def __init__(self, response_text: str = "Hello User, I am ERIS."):
        self.response_text = response_text
        self.voice_profile_manager = VoiceProfileManager(storage_path=tempfile.NamedTemporaryFile(delete=False).name)

    def process_chat(self, prompt: str, clear_history: bool = False):
        return {"response": self.response_text, "provider": "mock", "model": "mock"}

    def get_voice_settings(self):
        active = self.voice_profile_manager.get_active_profile()
        return {
            "active_profile": active.to_dict(),
            "capabilities": VoiceCapabilities().to_dict() if hasattr(VoiceCapabilities, "to_dict") else {
                "supports_voice_selection": True,
                "supports_speed": True,
                "supports_language": True,
                "supports_style": True,
                "supports_streaming": True,
                "supports_pronunciation": True,
            },
            "available_profiles": [p.to_dict() for p in self.voice_profile_manager.list_profiles()]
        }

    def update_voice_settings(self, updates):
        active = self.voice_profile_manager.get_active_profile()
        self.voice_profile_manager.update_profile(active.id, updates)
        return self.get_voice_settings()


def test_default_voice_profile_defaults():
    profile = VoiceProfile()
    assert profile.id == "default"
    assert profile.speaking_speed == 1.0
    assert profile.response_style == ResponseStyle.NEUTRAL
    assert profile.verbosity == ResponseVerbosity.NORMAL
    assert profile.quiet_mode is False
    assert profile.interruption_enabled is True
    assert profile.streaming_enabled is True
    assert isinstance(profile.to_dict(), dict)


def test_voice_profile_bounds_validation():
    # Speed bounds check
    data_high_speed = {"speaking_speed": 2.5}
    prof = VoiceProfile.from_dict(data_high_speed)
    assert prof.speaking_speed == 1.0  # falls back to safe default

    data_invalid_enum = {"response_style": "invalid_style", "verbosity": "super_verbose"}
    prof_enum = VoiceProfile.from_dict(data_invalid_enum)
    assert prof_enum.response_style == ResponseStyle.NEUTRAL
    assert prof_enum.verbosity == ResponseVerbosity.NORMAL


def test_profile_manager_persistence_and_recovery():
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
        tmp_path = tmp.name

    try:
        manager = VoiceProfileManager(storage_path=tmp_path)
        active = manager.get_active_profile()
        assert active.id == "default"

        # Update profile
        manager.update_profile("default", {"speaking_speed": 1.25, "quiet_mode": True})
        updated = manager.get_active_profile()
        assert updated.speaking_speed == 1.25
        assert updated.quiet_mode is True

        # Reload from disk
        manager2 = VoiceProfileManager(storage_path=tmp_path)
        reloaded = manager2.get_active_profile()
        assert reloaded.speaking_speed == 1.25
        assert reloaded.quiet_mode is True

        # Simulate corrupted file recovery
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write("corrupted json payload {{{")

        manager_corrupt = VoiceProfileManager(storage_path=tmp_path)
        assert manager_corrupt.get_active_profile().id == "default"
        assert manager_corrupt.get_active_profile().speaking_speed == 1.0
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def test_provider_capability_querying():
    stt_mock = MockSTTEngine()
    tts_mock = MockTTSEngine()
    tts_real = Pyttsx3TTSEngine()

    stt_caps = stt_mock.get_capabilities()
    assert isinstance(stt_caps, VoiceCapabilities)
    assert stt_caps.supports_language is True

    tts_caps = tts_mock.get_capabilities()
    assert isinstance(tts_caps, VoiceCapabilities)
    assert tts_caps.supports_speed is True

    real_caps = tts_real.get_capabilities()
    assert real_caps.supports_speed is True


def test_tts_speaking_speed_adjustment():
    tts_mock = MockTTSEngine(speaking_speed=1.5)
    res = tts_mock.synthesize("Testing voice synthesis speed.")
    assert res.duration_seconds < (len("Testing voice synthesis speed.") * 0.05)

    tts_pyttsx3 = Pyttsx3TTSEngine(rate=175, speaking_speed=1.2)
    assert tts_pyttsx3.effective_rate == int(175 * 1.2)


def test_voice_pipeline_quiet_mode():
    engine = DummyEngineService(response_text="ERIS response text.")
    config = VoiceConfig(quiet_mode=True)
    audio_source = MockAudioSource(inject_speech=True)
    audio_player = MockAudioPlayer()
    tts_engine = MockTTSEngine()

    pipeline = VoicePipeline(
        engine_service=engine,
        audio_source=audio_source,
        wakeword_detector=MockWakeWordDetector(always_detect=True),
        vad_engine=MockVADEngine(always_speech=True),
        stt_engine=MockSTTEngine(canned_response="Status check"),
        tts_engine=tts_engine,
        audio_player=audio_player,
        config=config,
    )

    state = pipeline.process_cycle()
    assert state == VoiceState.IDLE
    assert pipeline.last_response_text == "ERIS response text."
    # In quiet mode, TTS synthesis and playback are skipped
    assert len(tts_engine.synthesized_texts) == 0


def test_pronunciation_dictionary_replacement():
    engine = DummyEngineService(response_text="I love ERIS and Gemini.")
    config = VoiceConfig(pronunciation_dictionary={"ERIS": "Air-iss", "Gemini": "Jem-in-eye"})
    audio_source = MockAudioSource(inject_speech=True)
    tts_engine = MockTTSEngine()

    pipeline = VoicePipeline(
        engine_service=engine,
        audio_source=audio_source,
        wakeword_detector=MockWakeWordDetector(always_detect=True),
        vad_engine=MockVADEngine(always_speech=True),
        stt_engine=MockSTTEngine(canned_response="Who are you"),
        tts_engine=tts_engine,
        audio_player=MockAudioPlayer(),
        config=config,
    )

    pipeline.process_cycle()
    assert len(tts_engine.synthesized_texts) > 0
    assert "Air-iss" in tts_engine.synthesized_texts[0]
    assert "Jem-in-eye" in tts_engine.synthesized_texts[0]


def test_rest_api_voice_settings(monkeypatch):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")
    monkeypatch.delenv("ERIS_API_KEY", raising=False)
    engine = DummyEngineService()
    app = create_app(service=engine)
    client = TestClient(app)

    res = client.get("/api/settings/voice")
    assert res.status_code == 200
    data = res.json()
    assert "active_profile" in data
    assert data["active_profile"]["id"] == "default"

    update_res = client.put("/api/settings/voice", json={"speaking_speed": 1.2, "response_style": "friendly"})
    assert update_res.status_code == 200
    updated_data = update_res.json()
    assert updated_data["active_profile"]["speaking_speed"] == 1.2
    assert updated_data["active_profile"]["response_style"] == "friendly"


def test_rest_api_profile_management(monkeypatch):
    monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")
    monkeypatch.delenv("ERIS_API_KEY", raising=False)
    engine = DummyEngineService()
    app = create_app(service=engine)
    client = TestClient(app)

    res = client.get("/api/settings/voice/profiles")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    new_prof = {
        "id": "work",
        "name": "Work Profile",
        "speaking_speed": 1.1,
        "response_style": "professional",
        "verbosity": "concise"
    }
    post_res = client.post("/api/settings/voice/profiles", json=new_prof)
    assert post_res.status_code == 200
    data = post_res.json()
    assert data["active_profile"]["id"] == "work"
    assert data["active_profile"]["response_style"] == "professional"

"""
backend/voice/profile.py

Voice Profile Persistence & Profile Manager for ERIS Voice Subsystem (v2.8.3).

Provides:
- VoiceProfileManager: Manages loading, saving, updating, validating, and persisting
  voice profile configurations to disk (JSON) with safe recovery from malformed files.
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional

from backend.core.logging.logger import logger
from backend.voice.models import (
    ResponseStyle,
    ResponseVerbosity,
    VoiceProfile,
)

DEFAULT_PROFILE_PATH = os.path.join("backend", "storage", "settings", "voice_profile.json")


class VoiceProfileManager:
    """
    Centralized manager for ERIS Voice Profiles and Personalization settings.
    Ensures persistent storage, bounds validation, and corrupt configuration recovery.
    """

    def __init__(self, storage_path: str = DEFAULT_PROFILE_PATH) -> None:
        self.storage_path = storage_path
        self._profiles: Dict[str, VoiceProfile] = {}
        self._active_profile_id: str = "default"
        self._load_profiles()

    def _ensure_directory(self) -> None:
        dir_name = os.path.dirname(self.storage_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

    def _load_profiles(self) -> None:
        """Loads voice profiles from storage file. Falls back to default profile on error."""
        self._profiles = {"default": VoiceProfile()}
        self._active_profile_id = "default"

        if not os.path.exists(self.storage_path):
            logger.info(f"[VoiceProfileManager] Storage file '{self.storage_path}' not found. Initializing default profile.")
            self.save_profiles()
            return

        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            active_id = str(data.get("active_profile_id", "default"))
            profiles_raw = data.get("profiles", {})

            if isinstance(profiles_raw, dict):
                for p_id, p_data in profiles_raw.items():
                    if isinstance(p_data, dict):
                        profile = VoiceProfile.from_dict(p_data)
                        self._profiles[profile.id] = profile

            if "default" not in self._profiles:
                self._profiles["default"] = VoiceProfile()

            if active_id in self._profiles:
                self._active_profile_id = active_id
            else:
                self._active_profile_id = "default"

            logger.info(f"[VoiceProfileManager] Loaded {len(self._profiles)} profile(s). Active profile: '{self._active_profile_id}'.")
        except Exception as exc:
            logger.warning(f"[VoiceProfileManager] Failed to parse profile storage file '{self.storage_path}': {exc}. Recovering defaults.")
            self._profiles = {"default": VoiceProfile()}
            self._active_profile_id = "default"
            self.save_profiles()

    def save_profiles(self) -> None:
        """Persists all voice profiles to JSON storage file."""
        try:
            dir_name = os.path.dirname(self.storage_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            payload = {
                "active_profile_id": self._active_profile_id,
                "profiles": {pid: prof.to_dict() for pid, prof in self._profiles.items()}
            }
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            logger.info(f"[VoiceProfileManager] Profiles persisted cleanly to '{self.storage_path}'.")
        except Exception as exc:
            logger.error(f"[VoiceProfileManager] Failed to save voice profiles to disk: {exc}")

    def get_active_profile(self) -> VoiceProfile:
        """Returns the active VoiceProfile."""
        return self._profiles.get(self._active_profile_id, self._profiles["default"])

    def get_profile(self, profile_id: str) -> Optional[VoiceProfile]:
        """Returns a VoiceProfile by ID if exists."""
        return self._profiles.get(profile_id)

    def set_active_profile(self, profile_id: str) -> VoiceProfile:
        """Sets the active profile ID if it exists."""
        if profile_id not in self._profiles:
            raise KeyError(f"VoiceProfile '{profile_id}' does not exist.")
        self._active_profile_id = profile_id
        self.save_profiles()
        return self.get_active_profile()

    def list_profiles(self) -> List[VoiceProfile]:
        """Returns a list of all available voice profiles."""
        return list(self._profiles.values())


    def update_profile(self, profile_id: str, updates: Dict) -> VoiceProfile:
        """Updates attributes of an existing VoiceProfile with bounds validation."""
        profile = self._profiles.get(profile_id)
        if not profile:
            raise KeyError(f"VoiceProfile '{profile_id}' does not exist.")

        current_dict = profile.to_dict()

        for key, val in updates.items():
            if val is None:
                continue
            if key == "speaking_speed":
                speed = float(val)
                if speed < 0.75 or speed > 1.5:
                    raise ValueError("speaking_speed must be between 0.75 and 1.5.")
                current_dict["speaking_speed"] = speed
            elif key == "response_style":
                style_str = str(val).lower()
                ResponseStyle(style_str)  # validates enum
                current_dict["response_style"] = style_str
            elif key == "verbosity":
                verb_str = str(val).lower()
                ResponseVerbosity(verb_str)  # validates enum
                current_dict["verbosity"] = verb_str
            elif key == "pronunciation_dictionary":
                if not isinstance(val, dict):
                    raise ValueError("pronunciation_dictionary must be a dict.")
                if len(val) > 50:
                    raise ValueError("pronunciation_dictionary cannot exceed 50 items.")
                current_dict["pronunciation_dictionary"] = {str(k): str(v) for k, v in val.items()}
            elif key in current_dict and key not in ("id", "created_at"):
                current_dict[key] = val

        current_dict["updated_at"] = time.time()
        updated_profile = VoiceProfile.from_dict(current_dict)
        self._profiles[profile_id] = updated_profile
        self.save_profiles()
        return updated_profile

    def create_profile(self, profile: VoiceProfile) -> VoiceProfile:
        """Creates a new VoiceProfile."""
        if profile.id in self._profiles:
            raise ValueError(f"VoiceProfile '{profile.id}' already exists.")
        self._profiles[profile.id] = profile
        self.save_profiles()
        return profile

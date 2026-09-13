import json
import os
from typing import List, Dict, Optional
from backend.core.logging.logger import logger

class ConversationBuffer:
    def __init__(self, max_history: int = 20, storage_path: Optional[str] = None, persist_across_sessions: bool = False):
        # Stores history in a generic format: [{"role": "user", "text": "..."}, ...]
        self.history: List[Dict[str, str]] = []
        self.max_history = max_history
        self.storage_path = storage_path
        self.persist_across_sessions = persist_across_sessions

        if self.persist_across_sessions:
            self._load()

    def add_user_message(self, text: str):
        self.history.append({"role": "user", "text": text})
        self._trim()
        self._save()

    def add_assistant_message(self, text: str):
        self.history.append({"role": "assistant", "text": text})
        self._trim()
        self._save()

    def get_history(self) -> List[Dict[str, str]]:
        return self.history

    def clear(self):
        self.history = []
        self._save()

    def _trim(self):
        # Prevents context window overflow by trimming oldest messages
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]

    def _save(self):
        if self.storage_path:
            try:
                # Ensure the target directory exists
                os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
                with open(self.storage_path, 'w', encoding='utf-8') as f:
                    json.dump(self.history, f, indent=4)
            except Exception as e:
                logger.error(f"Failed to save memory to disk: {e}")

    def _load(self):
        if self.storage_path and os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load memory from disk: {e}")
                self.history = []
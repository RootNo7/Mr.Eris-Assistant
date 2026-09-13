import re
from typing import Optional, Dict, Any, List
from backend.core.logging.logger import logger
from backend.ai.memory.sqlite_memory import LongTermMemoryStore

class MemoryExtractor:
    """
    Automatic pattern-based memory fact extractor for ERIS.
    Scans user input prompts for explicit statements to store in long-term memory.
    """

    PATTERNS = [
        # "My name is Faisal" -> key="user_name", value="Faisal"
        (r"\bmy name is ([a-zA-Z0-9_ ]+)\b", "user_name", "user_profile"),
        # "Remember that my favorite editor is VS Code" -> key="favorite_editor", value="VS Code"
        (r"\bremember (?:that )?(?:my )?([a-zA-Z0-9_ ]+) is ([a-zA-Z0-9_\-\.\:\/ ]+)\b", None, "preference"),
        # "I prefer python for backend" -> key="preferred_language", value="python"
        (r"\bi prefer ([a-zA-Z0-9_\- ]+) for ([a-zA-Z0-9_\- ]+)\b", None, "preference"),
        # "My current project is ERIS Assistant" -> key="current_project", value="ERIS Assistant"
        (r"\bmy (?:current )?project is ([a-zA-Z0-9_\-\. ]+)\b", "current_project", "project"),
    ]

    def __init__(self, memory_store: LongTermMemoryStore):
        self.store = memory_store

    def extract_and_store(self, prompt: str) -> List[Dict[str, Any]]:
        """
        Parses user prompt and stores any extracted facts into long-term memory.
        Returns list of newly extracted fact dicts.
        """
        extracted = []
        text = prompt.strip()

        # 1. Explicit "My name is X"
        name_match = re.search(r"\bmy name is ([a-zA-Z0-9_ ]+)\b", text, re.IGNORECASE)
        if name_match:
            val = name_match.group(1).strip()
            fact = self.store.store_fact(key="user_name", value=val, category="user_profile")
            extracted.append(fact)

        # 2. Explicit "Remember that X is Y" or "Remember X is Y"
        remember_match = re.search(r"\bremember (?:that )?([a-zA-Z0-9_ ]+?) is ([a-zA-Z0-9_\-\.\:\/ ]+)", text, re.IGNORECASE)
        if remember_match:
            key_raw = remember_match.group(1).strip()
            val_raw = remember_match.group(2).strip()
            if key_raw and val_raw:
                fact = self.store.store_fact(key=key_raw, value=val_raw, category="user_fact")
                extracted.append(fact)

        # 3. Explicit "I prefer X for Y"
        prefer_match = re.search(r"\bi prefer ([a-zA-Z0-9_\- ]+) for ([a-zA-Z0-9_\- ]+)", text, re.IGNORECASE)
        if prefer_match:
            val_raw = prefer_match.group(1).strip()
            target_raw = prefer_match.group(2).strip()
            key_name = f"preferred_{target_raw.replace(' ', '_')}"
            fact = self.store.store_fact(key=key_name, value=val_raw, category="preference")
            extracted.append(fact)

        # 4. Explicit "My project is X"
        project_match = re.search(r"\bmy (?:current )?project is ([a-zA-Z0-9_\-\. ]+)", text, re.IGNORECASE)
        if project_match:
            val_raw = project_match.group(1).strip()
            fact = self.store.store_fact(key="current_project", value=val_raw, category="project")
            extracted.append(fact)

        return extracted

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from backend.core.config.settings import Config
from backend.tools.registry import ToolRegistry

class AIProvider(ABC):
    def __init__(self, config: Config, system_prompt: Optional[str] = None, tool_registry: Optional[ToolRegistry] = None):
        self.config = config
        self.system_prompt = system_prompt
        self.tool_registry = tool_registry
    """
    Abstract base class for all ERIS AI providers.
    Ensures the core system remains modular and provider-independent.
    """
    @abstractmethod
    def generate_response(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """
        Generate a response from the AI model.
        :param prompt: The current user input.
        :param history: Optional generic history buffer [{"role": "user"/"assistant", "text": "..."}]
        :param history: Optional generic history buffer
        """
        pass

    def generate_response_stream(self, prompt: str, history: Optional[List[Dict[str, str]]] = None):
        """
        Generate a response from the AI model as a stream.
        Generate a streamed response from the AI model, yielding text chunks.
        :param prompt: The current user input.
        :param history: Optional generic history buffer [{"role": "user"/"assistant", "text": "..."}]
        """
        pass

    def generate_step(
        self,
        prompt: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Generate one orchestration step: returns (thought_text, tool_call_intent | None).

        Default implementation calls generate_response() and parses the
        <<TOOL_CALL>>...</TOOL_CALL>> sentinel block so all existing providers
        automatically support the orchestration protocol without modification.

        Providers may override this method for more efficient or native parsing.

        :param prompt:  The orchestration step prompt (includes prior observations).
        :param history: Optional prior conversation history.
        :returns: Tuple of:
            - thought_text (str): Model reasoning or final answer text.
            - tool_call_intent (dict | None): {"name": str, "args": dict} or None.
        """
        import json
        import re

        _TOOL_CALL_RE = re.compile(
            r"<<TOOL_CALL>>\s*(\{.*?\})\s*<</TOOL_CALL>>",
            re.DOTALL | re.IGNORECASE,
        )

        raw = self.generate_response(prompt=prompt, history=history) or ""
        match = _TOOL_CALL_RE.search(raw)
        if not match:
            return raw, None

        try:
            payload = json.loads(match.group(1))
            if "name" not in payload:
                return raw, None
            if not isinstance(payload.get("args", {}), dict):
                payload["args"] = {}
            clean_thought = _TOOL_CALL_RE.sub("", raw).strip()
            return clean_thought, payload
        except json.JSONDecodeError:
            return raw, None
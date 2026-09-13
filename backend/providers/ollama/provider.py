from typing import List, Dict, Optional, Generator, Any
import json
import ollama
from backend.providers.base.provider import AIProvider
from backend.core.config.settings import Config
from backend.core.logging.logger import logger
from backend.core.exceptions import InvalidPromptError
from backend.tools.registry import ToolRegistry


class OllamaProvider(AIProvider):
    def __init__(self, config: Config, system_prompt: Optional[str] = None, tool_registry: Optional[ToolRegistry] = None):
        super().__init__(config, system_prompt, tool_registry)
        host = getattr(self.config, "OLLAMA_API_BASE", 'http://localhost:11434')
        self.client = ollama.Client(host=host)
        self.model_name = "qwen2.5-coder"
        logger.info(f"OllamaProvider initialized successfully with local model: {self.model_name}")

    def _build_messages(self, prompt: str, history: Optional[List[Dict[str, str]]]) -> List[Dict[str, Any]]:
        """Translates ERIS's generic history into Ollama's message format."""
        messages = []
        
        # 1. Inject Persona
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
            
        # 2. Inject Memory
        if history:
            for msg in history:
                messages.append({"role": msg.get("role", "user"), "content": msg.get("text") or msg.get("content", "")})
                
        # 3. Inject Current Prompt
        messages.append({"role": "user", "content": prompt})
        
        return messages

    def _get_tools_kwargs(self) -> Dict[str, Any]:
        if self.tool_registry:
            schemas = self.tool_registry.get_openai_schemas()
            if schemas:
                return {"tools": schemas}
        return {}

    def generate_response(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt cannot be empty or whitespace.")

        messages = self._build_messages(prompt, history)
        tools_kwargs = self._get_tools_kwargs()

        for _ in range(3):
            try:
                response = self.client.chat(
                    model=self.model_name,
                    messages=messages,
                    **tools_kwargs
                )
                message = response.get('message', {})
                tool_calls = message.get('tool_calls', [])

                if tool_calls:
                    messages.append(message)
                    for tc in tool_calls:
                        fn = tc.get('function', {})
                        tool_name = fn.get('name')
                        tool_args = fn.get('arguments', {})
                        if isinstance(tool_args, str):
                            try:
                                tool_args = json.loads(tool_args)
                            except Exception:
                                tool_args = {}

                        result = self.tool_registry.execute_tool_by_openai_name(tool_name, tool_args) if self.tool_registry else "Tool registry missing."
                        messages.append({
                            "role": "tool",
                            "content": str(result)
                        })
                    continue

                return message.get('content', '')
            except Exception as e:
                logger.error(f"OllamaProvider error: {e}")
                return "I encountered an error connecting to the local Ollama instance. Is the server running?"

        return ""

    def generate_response_stream(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> Generator[str, None, None]:
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt cannot be empty or whitespace.")

        messages = self._build_messages(prompt, history)
        tools_kwargs = self._get_tools_kwargs()

        for _ in range(3):
            try:
                response_stream = self.client.chat(
                    model=self.model_name,
                    messages=messages,
                    stream=True,
                    **tools_kwargs
                )
                
                tool_calls = []

                for chunk in response_stream:
                    msg = chunk.get('message', {})
                    content = msg.get('content', '')
                    if content:
                        yield content

                    if msg.get('tool_calls'):
                        tool_calls.extend(msg.get('tool_calls'))

                if not tool_calls:
                    break

                for tc in tool_calls:
                    fn = tc.get('function', {})
                    tool_name = fn.get('name', '')
                    tool_args = fn.get('arguments', {})
                    if isinstance(tool_args, str):
                        try:
                            tool_args = json.loads(tool_args)
                        except Exception:
                            tool_args = {}

                    yield f"\n\033[93m[ ERIS executing: {tool_name} ]\033[0m\n"

                    result = self.tool_registry.execute_tool_by_openai_name(tool_name, tool_args) if self.tool_registry else "Tool registry missing."

                    messages.append({
                        "role": "assistant",
                        "tool_calls": [tc]
                    })
                    messages.append({
                        "role": "tool",
                        "content": str(result)
                    })

            except Exception as e:
                logger.error(f"OllamaProvider streaming error: {e}")
                yield "\n[Local Connection Error: Verify Ollama is running in the background]"
                return
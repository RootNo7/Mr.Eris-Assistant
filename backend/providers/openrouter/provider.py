import json
from typing import List, Dict, Optional, Generator, Any
import openai
from backend.providers.base.provider import AIProvider
from backend.core.config.settings import Config
from backend.core.logging.logger import logger
from backend.tools.registry import ToolRegistry

from backend.core.exceptions import InvalidPromptError, ProviderInitializationError

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"


class OpenRouterProvider(AIProvider):
    """Concrete AIProvider implementation connecting to OpenRouter's multi-model API gateway."""

    def __init__(self, config: Config, system_prompt: Optional[str] = None, model_name: Optional[str] = None, tool_registry: Optional[ToolRegistry] = None):
        super().__init__(config, system_prompt, tool_registry)
        self.model_name = model_name or getattr(self.config, "OPENROUTER_MODEL", None) or DEFAULT_OPENROUTER_MODEL
        
        api_key = getattr(self.config, "OPENROUTER_API_KEY", None)
        if not api_key:
            raise ProviderInitializationError("OPENROUTER_API_KEY must be provided in Config for OpenRouterProvider.")

        self.client = openai.OpenAI(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
            default_headers={
                "HTTP-Referer": "https://github.com/Hafiz-Faisal902/Mr.Eris-Assistant",
                "X-Title": "ERIS Digital Assistant",
            }
        )
        logger.info(f"OpenRouterProvider initialized with model: {self.model_name}")

    def _build_messages(self, prompt: str, history: Optional[List[Dict[str, str]]]) -> List[Dict[str, Any]]:
        """Translates ERIS's generic conversation history into OpenAI/OpenRouter message format."""
        messages = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if history:
            for msg in history:
                role = "assistant" if msg.get("role") == "assistant" else "user"
                text = msg.get("text") or msg.get("content", "")
                messages.append({"role": role, "content": text})

        messages.append({"role": "user", "content": prompt})
        return messages

    def _get_tools_kwargs(self) -> Dict[str, Any]:
        """Returns kwargs containing tools schema for OpenAI client if tool_registry is available."""
        if self.tool_registry:
            schemas = self.tool_registry.get_openai_schemas()
            if schemas:
                return {"tools": schemas}
        return {}

    def generate_response(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Generates a synchronous text response from the OpenRouter model."""
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt cannot be empty or whitespace.")

        messages = self._build_messages(prompt, history)
        tools_kwargs = self._get_tools_kwargs()

        for _ in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    **tools_kwargs
                )
                if not response.choices:
                    return ""
                
                choice = response.choices[0]
                message = choice.message
                
                tool_calls = getattr(message, "tool_calls", None)
                if tool_calls and isinstance(tool_calls, list) and len(tool_calls) > 0:
                    messages.append(message)
                    for tc in tool_calls:
                        tool_name = tc.function.name
                        try:
                            tool_args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except Exception:
                            tool_args = {}

                        result = self.tool_registry.execute_tool_by_openai_name(tool_name, tool_args) if self.tool_registry else "Tool registry missing."
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result)
                        })
                    continue

                return message.content or ""
            except Exception as e:
                logger.error(f"OpenRouterProvider error: {e}")
                return f"I encountered an error connecting to OpenRouter: {e}"

        return ""

    def generate_response_stream(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> Generator[str, None, None]:
        """Streams text response chunks from OpenRouter with tool execution loop."""
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt cannot be empty or whitespace.")

        messages = self._build_messages(prompt, history)
        tools_kwargs = self._get_tools_kwargs()

        for _ in range(3):
            try:
                stream = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    stream=True,
                    **tools_kwargs
                )

                tool_calls_dict = {}

                for chunk in stream:
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta:
                        if getattr(delta, "content", None) and isinstance(delta.content, str):
                            yield delta.content

                        delta_tool_calls = getattr(delta, "tool_calls", None)
                        if delta_tool_calls and isinstance(delta_tool_calls, list):
                            for tc in delta_tool_calls:
                                idx = tc.index
                                if idx not in tool_calls_dict:
                                    tool_calls_dict[idx] = {
                                        "id": tc.id or f"call_{idx}",
                                        "name": tc.function.name if tc.function and tc.function.name else "",
                                        "arguments": tc.function.arguments if tc.function and tc.function.arguments else ""
                                    }
                                else:
                                    if tc.function and tc.function.name:
                                        tool_calls_dict[idx]["name"] += tc.function.name
                                    if tc.function and tc.function.arguments:
                                        tool_calls_dict[idx]["arguments"] += tc.function.arguments

                if not tool_calls_dict:
                    break

                # Process accumulated tool calls
                for idx, tc in tool_calls_dict.items():
                    tool_name = tc["name"]
                    raw_args = tc["arguments"]
                    tool_id = tc["id"]

                    try:
                        tool_args = json.loads(raw_args) if raw_args else {}
                    except Exception:
                        tool_args = {}

                    yield f"\n\033[93m[ ERIS executing: {tool_name} ]\033[0m\n"

                    result = self.tool_registry.execute_tool_by_openai_name(tool_name, tool_args) if self.tool_registry else "Tool registry missing."

                    messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tool_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": raw_args
                            }
                        }]
                    })

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": str(result)
                    })

            except Exception as e:
                logger.error(f"OpenRouterProvider streaming error: {e}")
                yield f"\n[OpenRouter Stream Error: {e}]"
                return


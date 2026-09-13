from google import genai
from google.genai import types
from backend.core.config.settings import Config
from backend.core.logging.logger import logger
from backend.providers.base.provider import AIProvider
from backend.core.exceptions import InvalidPromptError
from backend.tools.registry import ToolRegistry
from typing import Generator, List, Dict, Optional

DEFAULT_MODEL_NAME = "gemini-3.5-flash"


class GeminiProvider(AIProvider):
    """Concrete AIProvider implementation using the official google-genai SDK."""

    def __init__(self, config: Config, system_prompt: Optional[str] = None, tool_registry: Optional[ToolRegistry] = None):
        super().__init__(config, system_prompt, tool_registry)
        self.model_name = "gemini-3.5-flash"
        self.tool_registry = tool_registry
        self.client = None
        
        api_key = getattr(self.config, "GEMINI_API_KEY", None)
        if api_key and api_key != "your_gemini_api_key_here":
            try:
                self.client = genai.Client(api_key=api_key)
                logger.info("GeminiProvider initialized successfully with google-genai SDK.")
            except Exception as e:
                logger.warning(f"GeminiProvider SDK init deferred: {e}")

    def _build_contents(self, prompt: str, history: Optional[List[Dict[str, str]]]) -> List[types.Content]:
        """Helper method to format the conversation history and prompt for Gemini."""
        contents = []
        if history:
            for msg in history:
                role = "model" if msg["role"] == "assistant" else "user"
                contents.append(
                    types.Content(
                        role=role,
                        parts=[types.Part.from_text(text=msg["text"])]
                    )
                )
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )
        )
        return contents

    def _build_config(self) -> types.GenerateContentConfig:
        """Helper method to format the system instructions."""
        generation_config = types.GenerateContentConfig()
        if self.system_prompt:
            generation_config.system_instruction = self.system_prompt
        if self.tool_registry:
            callables = self.tool_registry.get_all_callables()
            if callables:
                generation_config.tools = callables
                
        return generation_config

    def _initialize_sdk(self) -> None:
        """Initializes the GenAI Client with the secure API key."""
        if self.client is not None:
            return
        api_key = getattr(self.config, "GEMINI_API_KEY", None)
        if not api_key or api_key == "your_gemini_api_key_here":
            raise RuntimeError("GEMINI_API_KEY is not configured.")
        try:
            self.client = genai.Client(api_key=api_key)
            logger.info("GeminiProvider initialized successfully with google-genai SDK.")
        except Exception as e:
            logger.error(f"Failed to initialize GeminiProvider: {e}")
            raise RuntimeError(f"GeminiProvider initialization failed: {e}") from e

    def generate_response(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> str:
        """Generates a synchronous response from the Gemini model."""
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt cannot be empty or whitespace.")

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=self._build_contents(prompt, history),
                config=self._build_config()
            )
            return response.text or ""
        except Exception as e:
            logger.error(f"GeminiProvider error: {e}")
            return "I encountered an error while processing your request."

    def generate_response_stream(self, prompt: str, history: Optional[List[Dict[str, str]]] = None) -> Generator[str, None, None]:
        """Streams the response chunk by chunk with secure tool-execution loop handling."""
        if not prompt or not prompt.strip():
            raise InvalidPromptError("Prompt cannot be empty or whitespace.")

        contents = self._build_contents(prompt, history)
        config = self._build_config()
        
        max_tool_iterations = 3  # Prevent infinite tool loops

        for _ in range(max_tool_iterations):
            try:
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name, contents=contents, config=config
                )
            except Exception as e:
                logger.error(f"GeminiProvider streaming error: {e}")
                yield f"\nI encountered an error while processing your request.\n{e}"
                return

            function_calls = []
            chunk_texts = []

            # 1. Read the stream safely
            try:
                for chunk in response_stream:
                    if chunk.text:
                        chunk_texts.append(chunk.text)
                        yield chunk.text
                    if chunk.function_calls:
                        function_calls.extend(chunk.function_calls)
            except Exception as stream_err:
                logger.error(f"Stream disconnection error: {stream_err}")
                # If we already yielded some text, don't crash hard, just break
                if not chunk_texts and not function_calls:
                    yield f"\n[ERIS Error: Server disconnected during stream]\n"
                break

            # 2. If no tools were requested, the response cycle is complete
            if not function_calls:
                break

            # 3. Execution Loop for Tools
            for fc in function_calls:
                tool_name = fc.name
                tool_args = dict(fc.args) if fc.args else {}
                
                # Yield UI notice safely
                yield f"\n\033[93m[ ERIS executing: {tool_name} ]\033[0m\n"
                
                # Execute securely via registry
                if self.tool_registry:
                    result = self.tool_registry.execute_tool(tool_name, tool_args)
                else:
                    result = "Error: Tool registry not initialized."
                
                # Append the AI's function call to history
                contents.append(types.Content(
                    role="model", 
                    parts=[types.Part.from_function_call(name=tool_name, args=tool_args)]
                ))
                
                # Append the physical result back as a function response part
                contents.append(types.Content(
                    role="user", 
                    parts=[types.Part.from_function_response(name=tool_name, response={"result": result})]
                ))
            
            # The loop automatically restarts, sending the tool result back to Gemini so it can formulate the final text response!
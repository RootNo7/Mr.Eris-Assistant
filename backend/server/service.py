import os
import threading
from typing import Dict, List, Any, Generator, Optional
from backend.core.config.settings import Config
from backend.core.logging.logger import logger
from backend.ai.persona.system import ERIS_SYSTEM_PROMPT
from backend.ai.memory.buffer import ConversationBuffer
from backend.ai.memory.sqlite_memory import LongTermMemoryStore
from backend.ai.memory.extractor import MemoryExtractor
from backend.tools.registry import ToolRegistry
from backend.tools.system_info import SystemInfoTool
from backend.tools.pc_tools import LaunchAppTool, OpenUrlTool, RunPCCommandTool
from backend.tools.file_tools import (
    ListFilesTool,
    SearchFilesTool,
    ReadFileTool,
    WriteFileTool,
    CreateDirectoryTool,
    CopyFileTool,
    MoveFileTool
)
from backend.core.version import VERSION
from backend.orchestration.loop import OrchestrationLoop
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.models import OrchestrationTask


from backend.voice.profile import VoiceProfileManager
from backend.voice.models import VoiceCapabilities, VoiceProfile
from backend.security.approval import ApprovalManager


class ERISEngineService:
    """
    Service wrapper encapsulating ERIS core engine state and capabilities.
    Allows API, CLI, and future interfaces to access ERIS services uniformly.
    """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

        # Initialize Approval System Manager (v2.9.1)
        self.approval_manager = ApprovalManager()

        # Initialize Tool Registry
        self.tool_registry = ToolRegistry()
        self.tool_registry.executor.approval_manager = self.approval_manager
        self.tool_registry.register(SystemInfoTool())
        self.tool_registry.register(LaunchAppTool())
        self.tool_registry.register(OpenUrlTool())
        self.tool_registry.register(RunPCCommandTool())
        self.tool_registry.register(ListFilesTool())
        self.tool_registry.register(SearchFilesTool())
        self.tool_registry.register(ReadFileTool())
        self.tool_registry.register(WriteFileTool())
        self.tool_registry.register(CreateDirectoryTool())
        self.tool_registry.register(CopyFileTool())
        self.tool_registry.register(MoveFileTool())

        # Initialize AI Provider
        self.provider = self._init_provider()

        # Initialize Memory Storage (Session Buffer & Long-Term Facts)
        memory_file = os.path.join(os.getcwd(), "backend", "storage", "memory", "session.json")
        self.memory = ConversationBuffer(max_history=20, storage_path=memory_file)
        self.long_term_memory = LongTermMemoryStore()
        self.memory_extractor = MemoryExtractor(self.long_term_memory)

        # Initialize Voice Profile Manager (v2.8.3)
        self.voice_profile_manager = VoiceProfileManager()

    def list_pending_approvals(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List active pending approval requests."""
        return [r.to_dict() for r in self.approval_manager.list_pending(session_id=session_id)]

    def get_approval(self, approval_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve approval request details by ID."""
        req = self.approval_manager.get_request(approval_id)
        return req.to_dict() if req else None

    def approve_request(self, approval_id: str, decided_by: str = "user") -> Dict[str, Any]:
        """Approve a pending approval request."""
        req = self.approval_manager.approve(approval_id, decided_by=decided_by)
        return req.to_dict()

    def reject_request(self, approval_id: str, decided_by: str = "user") -> Dict[str, Any]:
        """Reject a pending approval request."""
        req = self.approval_manager.reject(approval_id, decided_by=decided_by)
        return req.to_dict()

    def cancel_request(self, approval_id: str, decided_by: str = "user") -> Dict[str, Any]:
        """Cancel a pending approval request."""
        req = self.approval_manager.cancel(approval_id, decided_by=decided_by)
        return req.to_dict()


    def get_voice_settings(self) -> Dict[str, Any]:
        """Returns active voice profile, capabilities, and list of available profiles."""
        active = self.voice_profile_manager.get_active_profile()
        profiles = self.voice_profile_manager.list_profiles()
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
            "available_profiles": [p.to_dict() for p in profiles]
        }

    def update_voice_settings(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Updates attributes of the active voice profile."""
        active = self.voice_profile_manager.get_active_profile()
        updated = self.voice_profile_manager.update_profile(active.id, updates)
        return self.get_voice_settings()


    def _init_provider(self):
        active = self.config.ACTIVE_PROVIDER
        if active == "ollama":
            from backend.providers.ollama.provider import OllamaProvider
            return OllamaProvider(
                config=self.config,
                system_prompt=ERIS_SYSTEM_PROMPT,
                tool_registry=self.tool_registry
            )
        elif active == "openrouter":
            from backend.providers.openrouter.provider import OpenRouterProvider
            return OpenRouterProvider(
                config=self.config,
                system_prompt=ERIS_SYSTEM_PROMPT,
                tool_registry=self.tool_registry
            )
        else:
            from backend.providers.gemini.provider import GeminiProvider
            return GeminiProvider(
                config=self.config,
                system_prompt=ERIS_SYSTEM_PROMPT,
                tool_registry=self.tool_registry
            )

    @property
    def provider_name(self) -> str:
        return self.config.ACTIVE_PROVIDER

    @property
    def model_name(self) -> str:
        return getattr(self.provider, "model_name", "unknown")

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "version": VERSION,
            "active_provider": self.provider_name,
            "model": self.model_name,
            "auth_enabled": self.config.ERIS_AUTH_ENABLED
        }

    def get_providers_info(self) -> Dict[str, Any]:
        return {
            "active_provider": self.provider_name,
            "model_name": self.model_name,
            "supported_providers": ["gemini", "openrouter", "ollama"]
        }

    def get_tools_info(self) -> List[Dict[str, str]]:
        tools = []
        for tool_name in self.tool_registry.list_tools():
            tool = self.tool_registry.get_tool(tool_name)
            tools.append({
                "name": tool_name,
                "description": tool.description if tool else ""
            })
        return tools

    def get_memory(self) -> List[Dict[str, str]]:
        return self.memory.get_history()

    def clear_memory(self) -> None:
        self.memory.clear()

    def get_facts(self) -> List[Dict[str, Any]]:
        return self.long_term_memory.get_all_facts()

    def add_fact(self, key: str, value: str, category: str = "general") -> Dict[str, Any]:
        return self.long_term_memory.store_fact(key=key, value=value, category=category)

    def delete_fact(self, key: str) -> bool:
        return self.long_term_memory.delete_fact(key)

    def process_chat(self, prompt: str, clear_history: bool = False) -> Dict[str, str]:
        if clear_history:
            self.memory.clear()

        # 1. Extract potential new long-term memory facts from user prompt
        self.memory_extractor.extract_and_store(prompt)

        # 2. Recall relevant long-term facts matching query
        recalled_context = self.long_term_memory.format_recalled_facts_context(prompt)
        effective_prompt = f"{recalled_context}{prompt}" if recalled_context else prompt

        response_text = self.provider.generate_response(
            prompt=effective_prompt,
            history=self.memory.get_history()
        )

        self.memory.add_user_message(prompt)
        self.memory.add_assistant_message(response_text)

        return {
            "response": response_text,
            "provider": self.provider_name,
            "model": self.model_name
        }

    def process_chat_stream(self, prompt: str, clear_history: bool = False) -> Generator[str, None, None]:
        if clear_history:
            self.memory.clear()

        # 1. Extract potential new long-term memory facts from user prompt
        self.memory_extractor.extract_and_store(prompt)

        # 2. Recall relevant long-term facts matching query
        recalled_context = self.long_term_memory.format_recalled_facts_context(prompt)
        effective_prompt = f"{recalled_context}{prompt}" if recalled_context else prompt

        full_response = ""
        for chunk in self.provider.generate_response_stream(
            prompt=effective_prompt,
            history=self.memory.get_history()
        ):
            full_response += chunk
            yield chunk

        self.memory.add_user_message(prompt)
        self.memory.add_assistant_message(full_response)

    def process_orchestrated_chat(
        self,
        goal: str,
        config: Optional[OrchestrationConfig] = None,
        cancel_event: Optional[threading.Event] = None,
        clear_history: bool = False,
    ) -> OrchestrationTask:
        """
        Execute a goal through the controlled ERIS Orchestration Loop.

        Unlike process_chat(), which is a single-turn call to the provider,
        this method runs the full think → act → observe cycle with safety
        governors (max_steps, max_tool_calls, max_execution_seconds).

        All tool calls are routed through CentralToolExecutor as usual.

        Parameters
        ----------
        goal : str
            The user's goal or question.
        config : OrchestrationConfig | None
            Safety governor overrides.  Defaults to OrchestrationConfig().
        cancel_event : threading.Event | None
            Pass a pre-created event to support external cancellation.
            A new Event is created per call when not provided.
        clear_history : bool
            When True, clears the session conversation buffer before running.

        Returns
        -------
        OrchestrationTask
            Complete task record in a terminal state.
        """
        if clear_history:
            self.memory.clear()

        # Recall relevant long-term facts and inject into the goal context
        recalled_context = self.long_term_memory.format_recalled_facts_context(goal)
        effective_goal = f"{recalled_context}{goal}" if recalled_context else goal

        orch_config = config or OrchestrationConfig.default()
        event = cancel_event or threading.Event()

        loop = OrchestrationLoop(
            provider=self.provider,
            tool_registry=self.tool_registry,
            config=orch_config,
            cancel_event=event,
        )

        task = loop.run(goal=effective_goal, history=self.memory.get_history())

        # Store the final answer (if any) in conversation memory
        if task.final_answer:
            self.memory.add_user_message(goal)
            self.memory.add_assistant_message(task.final_answer)

        return task

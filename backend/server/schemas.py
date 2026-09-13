from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any

class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="User prompt text")
    clear_history: bool = Field(default=False, description="Optionally clear conversation context before processing prompt")

class ChatResponse(BaseModel):
    response: str = Field(..., description="Assistant response text")
    provider: str = Field(..., description="Name of the active AI provider")
    model: str = Field(..., description="Name of active AI model")

class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Server health status")
    version: str = Field(..., description="ERIS system version")
    active_provider: str = Field(..., description="Currently active AI provider")
    model: str = Field(..., description="Currently active AI model")
    auth_enabled: bool = Field(default=False, description="Whether API key authentication is required")

class MemoryResponse(BaseModel):
    history: List[Dict[str, str]] = Field(..., description="List of conversation turns")
    count: int = Field(..., description="Total message count in context window")

class ToolInfo(BaseModel):
    name: str = Field(..., description="Tool registration name")
    description: str = Field(..., description="Tool functionality description")

class ToolsResponse(BaseModel):
    tools: List[ToolInfo] = Field(..., description="List of available PC/system tools")
    count: int = Field(..., description="Number of registered tools")

class ProviderInfo(BaseModel):
    active_provider: str = Field(..., description="Currently active AI provider")
    model_name: str = Field(..., description="Model name in use")
    supported_providers: List[str] = Field(..., description="Supported AI providers")

class FactSchema(BaseModel):
    key: str = Field(..., description="Fact key name")
    value: str = Field(..., description="Fact detail value")
    category: str = Field(default="general", description="Fact category taxonomy")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp of creation")
    updated_at: Optional[str] = Field(default=None, description="ISO timestamp of last update")

class FactCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, description="Fact key name")
    value: str = Field(..., min_length=1, description="Fact value")
    category: str = Field(default="general", description="Category tag")

class FactsResponse(BaseModel):
    facts: List[FactSchema] = Field(..., description="List of stored long-term memory facts")
    count: int = Field(..., description="Total fact count")


# ---------------------------------------------------------------------------
# Orchestration Schemas (v2.6.0)
# ---------------------------------------------------------------------------

class OrchestrationRequest(BaseModel):
    """Request body for POST /api/orchestrate."""
    goal: str = Field(..., min_length=1, description="The user goal or question to orchestrate")
    max_steps: Optional[int] = Field(
        default=None, ge=1, le=100,
        description="Override maximum orchestration steps (default: 10)"
    )
    max_tool_calls: Optional[int] = Field(
        default=None, ge=1, le=200,
        description="Override maximum total tool calls (default: 20)"
    )
    max_seconds: Optional[float] = Field(
        default=None, ge=5.0, le=600.0,
        description="Override maximum wall-clock execution time in seconds (default: 120)"
    )
    clear_history: bool = Field(
        default=False,
        description="Optionally clear conversation context before orchestrating"
    )


class OrchestrationStepSchema(BaseModel):
    """Serialised representation of one orchestration step for API responses."""
    step_index: int
    status: str
    thought: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    observation: Optional[str] = None
    retry_count: int = 0


class OrchestrationResponse(BaseModel):
    """Response body for POST /api/orchestrate."""
    task_id: str = Field(..., description="Unique task identifier (UUID)")
    goal: str = Field(..., description="The original user goal")
    status: str = Field(..., description="Terminal task status")
    step_count: int = Field(..., description="Total steps executed")
    tool_call_count: int = Field(..., description="Total tool invocations")
    elapsed_seconds: float = Field(..., description="Wall-clock time for the task")
    final_answer: Optional[str] = Field(default=None, description="Final answer when status=completed")
    error: Optional[str] = Field(default=None, description="Error detail when task did not complete")
    steps: List[OrchestrationStepSchema] = Field(..., description="Full step-by-step execution trace")


# ---------------------------------------------------------------------------
# Voice Settings & Personalization Schemas (v2.8.3)
# ---------------------------------------------------------------------------

class VoiceCapabilitiesSchema(BaseModel):
    supports_voice_selection: bool = True
    supports_speed: bool = True
    supports_language: bool = True
    supports_style: bool = True
    supports_streaming: bool = True
    supports_pronunciation: bool = True


class VoiceProfileSchema(BaseModel):
    id: str = Field(default="default", description="Profile unique identifier")
    name: str = Field(default="Default Voice Profile", description="Profile display name")
    enabled: bool = Field(default=True, description="Whether profile is enabled")
    language: str = Field(default="en-US", description="Target locale / language code")
    locale: str = Field(default="en-US", description="Locale tag")
    voice_id: str = Field(default="default", description="TTS voice identifier")
    speaking_speed: float = Field(default=1.0, ge=0.75, le=1.5, description="Speaking speed rate multiplier (0.75-1.5)")
    response_style: str = Field(default="neutral", description="Voice response tone/style (neutral, direct, friendly, professional)")
    verbosity: str = Field(default="normal", description="Response verbosity (concise, normal, detailed)")
    wake_word: str = Field(default="eris", description="Wake word keyword")
    wake_word_enabled: bool = Field(default=True, description="Whether wake word engine is active")
    wake_word_sensitivity: float = Field(default=0.5, ge=0.0, le=1.0, description="Wake word detection threshold")
    quiet_mode: bool = Field(default=False, description="Whether quiet mode (non-spoken audio) is active")
    interruption_enabled: bool = Field(default=True, description="Whether barge-in interruption is active")
    streaming_enabled: bool = Field(default=True, description="Whether sentence streaming is active")
    pronunciation_dictionary: Dict[str, str] = Field(default_factory=dict, description="Pronunciation replacement dictionary")


class VoiceSettingsUpdateSchema(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    voice_id: Optional[str] = None
    speaking_speed: Optional[float] = Field(default=None, ge=0.75, le=1.5)
    response_style: Optional[str] = None
    verbosity: Optional[str] = None
    wake_word: Optional[str] = None
    wake_word_enabled: Optional[bool] = None
    wake_word_sensitivity: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    quiet_mode: Optional[bool] = None
    interruption_enabled: Optional[bool] = None
    streaming_enabled: Optional[bool] = None
    pronunciation_dictionary: Optional[Dict[str, str]] = None


class VoiceSettingsResponse(BaseModel):
    active_profile: VoiceProfileSchema
    capabilities: VoiceCapabilitiesSchema
    available_profiles: List[VoiceProfileSchema]


# ---------------------------------------------------------------------------
# Approval System Schemas (v2.9.1)
# ---------------------------------------------------------------------------

class ApprovalRequestSchema(BaseModel):
    approval_id: str
    request_id: str
    session_id: Optional[str] = None
    principal_id: str
    tool_name: str
    action: str
    arguments: Dict[str, Any]
    resource_scope: str
    permission: str
    risk_level: int
    reason: str
    created_at: float
    expires_at: float
    state: str
    decided_at: Optional[float] = None
    decided_by: Optional[str] = None
    binding_hash: str
    used: bool
    is_expired: bool


class ApprovalListResponse(BaseModel):
    approvals: List[ApprovalRequestSchema]
    count: int


class ApprovalActionRequest(BaseModel):
    decided_by: str = Field(default="user", description="Identity of principal making decision")


class ApprovalActionResponse(BaseModel):
    status: str
    message: str
    approval: ApprovalRequestSchema



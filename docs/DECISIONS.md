# ERIS — Decision Log

Format per decision: Decision / Reason / Alternatives considered /
Trade-offs / Status.

---

## D-001: Provider abstraction via `AIProvider` ABC

- **Decision:** All AI providers implement an abstract `AIProvider` base
  class with a single `generate_response(prompt: str) -> str` method.
  Core/CLI code depends only on this interface, never on a concrete SDK.
- **Reason:** Manual requirement — core logic must never be tightly
  coupled to one vendor. Enables adding OpenAI/Claude/local models later
  without touching `apps/cli/main.py`.
- **Alternatives considered:** Direct SDK calls in the CLI (rejected —
  blocks future provider swaps); duck-typing without an ABC (rejected —
  ABC gives an explicit, enforced contract and clearer errors at
  class-definition time if a provider is incomplete).
- **Trade-offs:** Slightly more boilerplate per provider (must subclass
  and implement the method) in exchange for real interchangeability.
- **Status:** Implemented.

## D-002: Fail-fast configuration validation

- **Decision:** `Config.__init__()` calls `self.validate()` immediately,
  raising `ValueError` if `GEMINI_API_KEY` is missing. The CLI wraps
  `Config()` construction in try/except and aborts boot on failure.
- **Reason:** A missing secret should produce one clear error at startup,
  not a confusing failure three layers deep inside a provider call.
- **Alternatives considered:** Lazy validation (check the key only when
  first used) — rejected, produces worse error locality and could let
  the app appear to start successfully before failing mid-conversation.
- **Trade-offs:** None significant at this scale.
- **Status:** Implemented.

## D-003: Single centralized logger factory

- **Decision:** One `get_logger(name)` factory in
  `backend/core/logging/logger.py`, guarding against duplicate handlers,
  with a module-level `logger = get_logger("ERIS")` for convenience.
- **Reason:** Consistent formatting and log level across the whole app;
  avoids the common bug of duplicate log lines from repeated
  `logging.getLogger()` + `addHandler()` calls.
- **Alternatives considered:** Per-module ad hoc `logging.basicConfig()`
  calls — rejected, fragile and inconsistent across modules.
- **Trade-offs:** None significant at this scale.
- **Status:** Implemented.

## D-004: Secrets only via `.env`, never hardcoded

- **Decision:** All secrets (currently `GEMINI_API_KEY`) load via
  `python-dotenv` from `.env`, which is git-ignored. `.env.example`
  ships with placeholder values only.
- **Reason:** Manual requirement — never commit secrets. Standard
  practice for personal + shareable projects.
- **Alternatives considered:** OS keyring / secret manager — deferred as
  overkill for a single-user local CLI at this stage; revisit if ERIS
  gains multi-user support or cloud deployment.
- **Trade-offs:** `.env` file itself is only as secure as the local
  filesystem — acceptable for current single-user, local-first scope.
- **Status:** Implemented.

## D-005: Repo layout — `apps/` vs `backend/` split

- **Decision:** Entry points live under `apps/` (currently just `cli/`);
  all engine logic lives under `backend/`. Tests mirror `backend/`
  structure under `tests/unit/`.
- **Reason:** Keeps interface code (things that change per platform:
  CLI today, desktop UI/voice later) separate from core logic that
  should be interface-agnostic. A future desktop or voice interface adds
  a new folder under `apps/` without touching `backend/`.
- **Alternatives considered:** Flat single-package layout — rejected,
  would blur the interface/core boundary as more interfaces are added.
- **Trade-offs:** Slightly more nesting for a project this small, in
  exchange for a layout that doesn't need restructuring later.
- **Status:** Implemented.

## D-006: `LICENCE` file added, MIT chosen

- **Decision:** Added an MIT `LICENCE` file. `pyproject.toml` already
  referenced `license = { file = "LICENCE" }` but the file didn't exist
  in the repo, which would break `pip install -e .` at the build
  metadata step.
- **Reason:** MIT chosen as a sensible permissive default for a personal
  project with no stated licensing requirement.
- **Alternatives considered:** Not specified by project owner at time of
  writing.
- **Trade-offs:** None — this is a placeholder pending explicit owner
  preference.
- **Status:** Implemented, **owner should confirm or override.**

## D-007: `docs/` scaffolding added (this file and siblings)

- **Decision:** Added `ARCHITECTURE.md`, `DECISIONS.md`, `ROADMAP.md`,
  `CHANGELOG.md`, `TESTING.md`, `PROJECT_STATE.md` under `docs/`.
- **Reason:** Manual requirement (§24, §52, §60) — architectural
  decisions and project state must live in the repo, not only in chat
  history, so development can resume across sessions without lost
  context.
- **Alternatives considered:** Rely on chat memory only — rejected, does
  not survive a new session, a new machine, or a different assistant.
- **Trade-offs:** Requires discipline to keep updated as the project
  moves — worth it for a multi-year project.
- **Status:** Implemented.

## D-008: OpenRouter Multi-Model Gateway Provider Integration

- **Decision:** Implemented `OpenRouterProvider` (`backend/providers/openrouter/provider.py`) using the official `openai` SDK configured with OpenRouter's `base_url="https://openrouter.ai/api/v1"`.
- **Reason:** Provides ERIS with seamless access to free flagship models (e.g. Meta Llama 3.3 70B Free, DeepSeek R1 Free, Qwen 2.5 72B Free) via a single unified API, upholding ERIS Charter §40 (Free first -> cheap second -> premium when justified) and §10 (Provider Abstraction).
- **Alternatives considered:** Building individual custom HTTP client code for every vendor — rejected as high maintenance when OpenRouter provides an OpenAI-compatible interface.
- **Trade-offs:** Requires an OpenRouter API key when selected, but provides immediate access to dozens of models without adding custom provider modules for each model.
- **Status:** Implemented in v0.1.9.

## D-009: Decoupled REST & SSE API Layer using FastAPI

- **Decision:** Wrap the ERIS core engine in a FastAPI application (`backend/server/app.py`) managed by an `ERISEngineService` wrapper (`backend/server/service.py`) and launched via `apps/api/main.py`. Expose REST endpoints for health, providers, tools, and memory, and an SSE endpoint (`/api/chat/stream`) for text chunk streaming.
- **Reason:** Milestone v2.1 requirement — decouples ERIS core engine from user interfaces, enabling the upcoming ERIS v2.2 Web UI (and future mobile/remote interfaces) to interact with ERIS over standard HTTP/SSE protocols.
- **Alternatives considered:** Custom socket server (rejected — lacks standard OpenAPI docs and HTTP validation); WebSockets-only (rejected — SSE is simpler, lighter, and resilient for uni-directional streaming chat completions).
- **Trade-offs:** Introduces `fastapi` and `uvicorn` dependencies to `pyproject.toml`.
- **Status:** Implemented in v2.1.0.

## D-010: ChatGPT-Style Web UI Client with Zero-Dependency Static Server Integration

- **Decision:** Build a responsive, glassmorphism ChatGPT-style Web UI (`apps/web/index.html`, `apps/web/src/css/style.css`, `apps/web/src/js/`) featuring real-time SSE response streaming, collapsible sidebar drawer, live system status polling, tool registry inspector, and memory clearing. Serve the web application statically via FastAPI (`app.mount("/", StaticFiles(...))`).
- **Reason:** Milestone v2.2 requirement — provides an intuitive, high-aesthetic web interface for interacting with ERIS from any browser on local networks without needing separate frontend node build steps or runtime dependencies.
- **Alternatives considered:** Complex SPA build tools (React/Vite with npm dependencies) — deferred for now as unnecessary complexity when native ES modules + CSS design system provides instant load times and zero-dependency static mounting via FastAPI.
- **Trade-offs:** None.
- **Status:** Implemented in v2.2.0.

## D-011: Configurable API Key Authentication & Zero-Trust Remote Access

- **Decision:** Implement configurable API key authentication (`ERIS_AUTH_ENABLED=true/false` and `ERIS_API_KEY`) using FastAPI security dependency `verify_api_key` (`backend/server/auth.py`). Inspect `X-ERIS-API-Key` or `Authorization: Bearer <key>` headers. Add Web UI Auth Modal for key entry, persisting the key in browser `localStorage`.
- **Reason:** Milestone v2.3 requirement (Phase B Secure Remote Access) — protects ERIS against unauthorized access when exposed over local networks or zero-trust remote tunnels (Tailscale / Cloudflare Tunnel).
- **Alternatives considered:** Complex OAuth2 / JWT identity server — deferred as over-engineering for single-user personal access; API token header with constant-time HMAC comparison provides robust protection with zero external dependencies.
- **Trade-offs:** Requires entering key once in Web UI when auth is enabled.
- **Status:** Implemented in v2.3.0.

## D-012: Persistent SQLite Long-Term Memory & Automatic Fact Extraction

- **Decision:** Build a zero-dependency SQLite storage engine (`LongTermMemoryStore` in `backend/ai/memory/sqlite_memory.py`) paired with pattern-based automatic fact extraction (`MemoryExtractor` in `backend/ai/memory/extractor.py`). Expose CRUD REST endpoints `/api/memory/facts` and a Memory Facts Inspector panel in the Web UI sidebar.
- **Reason:** Milestone v2.4 requirement — enables ERIS to remember user facts, preferences, system details, and project state persistently across sessions and AI provider swaps.
- **Alternatives considered:** Vector database (e.g. Chroma/Qdrant) — deferred as vector DB dependencies add heavy overhead; SQLite with keyword/category indexing provides instant local performance, zero installation complexity, and complete privacy.
- **Trade-offs:** Requires simple regex/pattern rules for automatic extraction alongside explicit manual fact editing in Web UI.
- **Status:** Implemented in v2.4.0.

## D-013: Centralized Version Management & Backward-Compatible Exception Taxonomy

- **Decision:** Establish `backend/core/version.py` (`__version__ = "2.4.1"`) as the single authoritative source of version information across ERIS. Create structured exception classes in `backend/core/exceptions.py` inheriting from both `ERISError` base class and standard Python built-in exceptions (`ValueError`, `RuntimeError`, `KeyError`). Refactor `Config` (`backend/core/config/settings.py`) to raise `ConfigurationError`. Complete `ToolRegistry` with `list_tools()`.
- **Reason:** Milestone v2.4.1 foundation hardening — eliminates version string duplication across package metadata, REST API responses, Web UI HTML badges, and CLI headers. Structured exception classes provide explicit error classification while multi-inheritance guarantees 100% backward compatibility for existing `try/except ValueError` call sites.
- **Alternatives considered:** Reading version at runtime via `importlib.metadata` (rejected as fragile in non-installed source runs); breaking exception hierarchy without subclassing built-in exceptions (rejected as it would break callers and existing unit test assertions).
- **Trade-offs:** Requires importing `backend.core.version` across entry points and consumers.
- **Status:** Implemented in v2.4.1.

## D-014: Centralized Executable Action Permission Framework & Audit Engine

- **Decision:** Implement a code-enforced, provider-independent Action Permission Framework (`backend/security/`). Categorize tools into 5 risk levels (T0 Read-Only, T1 Low Risk, T2 Medium Risk, T3 High Risk / Terminal, T4 Critical System Operations). Force ALL tool calls across Gemini, OpenRouter, and Ollama through a single central chokepoint (`CentralToolExecutor` in `backend/security/executor.py`) which enforces signature validation, risk policy checks (`PolicyEngine`), approval gating (`ApprovalGate`), timeout handling (`ThreadPoolExecutor`), structured JSON Lines audit logging (`AuditLogger`), and safe denial formatting (`[SECURITY DENIAL] ...`).
- **Reason:** Critical security requirement — security rules must be strictly enforced in executable application code, NOT in LLM system prompts or keyword filters. Provider-independent architecture ensures identical security policy enforcement across cloud and local models.
- **Alternatives considered:** Relying on system prompt guardrails (rejected — vulnerable to prompt injection); ad hoc security checks inside individual tool `execute` methods (rejected — fragile, lacks central audit logging and policy management).
- **Trade-offs:** Adds ~3ms of policy evaluation and argument validation overhead per tool execution.
- **Status:** Implemented in v2.5.0.

## D-015: Secure Filesystem Tool Subsystem with PathGuard and Dependency-Injectable Design

- **Decision:** Implement a dedicated `PathGuard` class (`backend/security/path_guard.py`) as the exclusive security gatekeeper for all 7 filesystem tools. `PathGuard` canonicalizes paths via `os.path.realpath()`, verifies targets against explicit allowed root directories (`ERIS_ALLOWED_FS_ROOTS`), rejects traversal patterns, guards symlink escapes, and enforces file size limits. All tool classes accept `PathGuard` as an optional constructor parameter, defaulting to the global production guard.
- **Reason:** Filesystem access requires a defense-in-depth approach beyond the `PolicyEngine` and `CentralToolExecutor` layer. Path traversal (`../../../etc/passwd`), symlink escapes, and unbounded file reads are well-known attack vectors that must be blocked at the path resolution layer before any OS call is made. Dependency injection enables deterministic, isolated unit testing without modifying `os.getcwd()` process state.
- **Alternatives considered:** Monkeypatching `os.getcwd()` in tests (rejected — fragile and order-dependent); hardcoding a single global `path_guard` instance (rejected — prevents scoped testing and breaks isolation); using only regex-based path filtering (rejected — canonicalization is required to defeat encoded traversal patterns).
- **Trade-offs:** Each tool class requires a constructor parameter, slightly increasing instantiation verbosity. Production use remains zero-configuration (guard defaults apply automatically).
- **Status:** Implemented.

## D-016: Controlled Single-Agent Orchestration Loop with Sentinel-Based Provider Protocol

- **Decision:** Implement a dedicated orchestration package (`backend/orchestration/`) introducing `OrchestrationLoop`, `OrchestrationConfig`, `OrchestrationTask`, and `OrchestrationStep`. The loop executes a structured think → act → observe cycle governed by 3 non-bypassing limits (`max_steps`, `max_tool_calls`, `max_execution_seconds`). Providers signal tool call intent using standard `<<TOOL_CALL>>...<</TOOL_CALL>>` JSON sentinel markers. All tool calls route through `ToolRegistry.execute_tool()` → `CentralToolExecutor`.
- **Reason:** Milestone v2.6 requirement — converts single-turn prompt-response chat into an agentic execution loop capable of task decomposition, tool invocation, observation, and verification. Sentinel markers ensure complete provider independence across Gemini, OpenRouter, and Ollama without tight coupling to SDK-specific tool calling formats.
- **Alternatives considered:** Hardcoding provider-specific SDK function-calling loops inside individual provider implementations (rejected — violates Provider Abstraction principle D-001 and duplicates loop logic); using an external multi-agent framework like AutoGen/CrewAI (rejected — violates §50 "do not overengineer" and adds heavy third-party dependencies).
- **Trade-offs:** Requires providers to format tool call intent as `<<TOOL_CALL>>...<</TOOL_CALL>>` when orchestration mode prompt addendum is injected.
- **Status:** Implemented in v2.6.0.

## D-017: Modular Hardware-Abstracted Voice Subsystem Architecture

- **Decision:** Implement a dedicated voice interface subsystem under `backend/voice/` and entry point under `apps/voice/`. Abstract all audio hardware and processing modules behind abstract base classes (`AudioSource`, `WakeWordDetector`, `VADEngine`, `STTEngine`, `TTSEngine`, `AudioPlayer`). Implement zero-hardware mock doubles (`MockAudioSource`, `MockWakeWordDetector`, `MockVADEngine`, `MockSTTEngine`, `MockTTSEngine`, `MockAudioPlayer`) for CI/CD test automation. Route all transcribed voice commands through `ERISEngineService` and `CentralToolExecutor`.
- **Reason:** Milestone v2.7 requirement — provides a hands-free voice interface for ERIS (`Microphone → Wake Word → VAD → STT → ERIS Core → TTS → Speaker`) without introducing tight coupling to specific operating system audio drivers or third-party binaries. Ensures 100% testability on environments without physical microphones or speakers, and guarantees all spoken commands obey the Action Permission Framework and approval gates.
- **Alternatives considered:** Embedding voice processing inside provider classes (rejected — violates interface isolation and provider abstraction principles D-001); using monolithic cloud voice APIs (rejected — violates local-first design and adds unwanted external cloud dependencies).
- **Trade-offs:** Requires modular adapter classes for each audio component, slightly increasing package count.
- **Status:** Implemented in v2.7.0.

## D-018: Deterministic Voice Interaction State Machine & Turn Isolation Engine

- **Decision:** Enhance the ERIS Voice Subsystem (`backend/voice/`) with a deterministic state machine validator (`transition_to()`), explicit states (`IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SPEAKING`, `INTERRUPTED`, `CANCELLED`, `PAUSED_FOR_APPROVAL`, `ERROR`), atomic `generation_token` counter, UUID `turn_id` tracking, barge-in interruption (`interrupt()`), turn cancellation (`cancel_turn()`), sentence-level TTS streaming buffer output, latency metrics (`VoiceTurnMetrics`), user-friendly error mappings, and structured logging.
- **Reason:** Milestone v2.8.1 Voice UX requirement — guarantees responsive, predictable, and interruptible voice interaction. Prevents stale asynchronous response chunks from leaking into subsequent turns when a user interrupts or cancels. Sentence-level streaming significantly lowers time-to-first-audio without compromising provider abstraction or engine safety.
- **Alternatives considered:** Relying on simple boolean flags for cancellation (rejected — vulnerable to race conditions where old turn audio chunks arrive after state resets); token-level TTS streaming (rejected — sentence-level TTS is far safer, avoids robotic phoneme fragment jitter, and requires no provider-specific SDK hacks inside the voice layer).
- **Trade-offs:** Adds ~10 lines of transition validation logic and regex sentence boundary splitting.
- **Status:** Implemented in v2.8.1.

## D-019: Subsystem Health Monitoring, Timeout Guards & Stale-Result Protection Architecture

- **Decision:** Enhance the ERIS Voice Subsystem (`backend/voice/`) with high-level subsystem health tracking (`VoiceHealthState`: `HEALTHY`, `DEGRADED`, `FAILED`, `RECOVERING`), strict 2-way stale result checking (`turn_id` + `generation_token`), explicit stage timeout guards (`VoiceTimeouts`), bounded retries with exponential backoff for transient failures (`VoiceRetryConfig`), thread-safe playback locking, deterministic session reset (`reset_session()`), and `try...finally` resource cleanup wrappers.
- **Reason:** Milestone v2.8.2 Voice Reliability requirement — converts ERIS voice from a responsive UX prototype into a trustworthy, recoverable, and predictable interface resilient to hardware disconnects, provider timeouts, transient engine errors, and race conditions during long-session operations.
- **Alternatives considered:** Relying on process restart for recovery on hardware/STT/TTS errors (rejected — breaks daemon execution and user experience); infinite retry loops (rejected — leads to retry storms, resource starvation, and process freezes).
- **Trade-offs:** Adds timeout and retry dataclasses to `VoiceConfig`, slightly increasing configuration options.
- **Status:** Implemented in v2.8.2.

## D-020: Voice Profile Personalization & Capability Querying Architecture

- **Decision:** Implement structured voice profile management (`VoiceProfile`, `VoiceProfileManager`), persistent JSON configuration (`backend/storage/settings/voice_profile.json`), provider capability abstraction (`VoiceCapabilities`), quiet mode support (suppresses spoken output while keeping text response), pronunciation override replacement dictionary, and REST API settings endpoints (`GET/PUT /api/settings/voice`).
- **Reason:** Milestone v2.8.3 Voice Personalization requirement — enables users to customize voice IDs, speaking speed rates (0.75x to 1.5x), response styles, verbosity levels, language/locales, wake-word parameters, quiet mode, and pronunciation overrides without modifying core application code or breaking provider independence. Corrupted config files fall back cleanly to safe defaults (`default` profile).
- **Alternatives considered:** Hardcoding user preferences inside provider implementations (rejected — violates separation of concerns and provider independence D-001); using ad-hoc environment variables for every voice option (rejected — environmental variables cannot be dynamically updated via REST API or UI at runtime).
- **Trade-offs:** Adds `VoiceProfileManager` and REST API schemas for voice settings.
- **Status:** Implemented in v2.8.3.

## D-021: Centralized Permission Engine & 8-Stage Deterministic Evaluation Architecture

- **Decision:** Implement a centralized `PermissionEngine` (`backend/security/engine.py`) and strongly-typed data models (`backend/security/permissions.py`: `Permission`, `Principal`, `ResourceScope`, `PermissionRequest`, `PermissionContext`, `PermissionDecision`) acting as the mandatory security boundary in application code for all tool executions across CLI, REST API, Voice daemon, and AI providers. Enforce a deterministic 8-stage evaluation precedence order:
  1. Stage 1: Global Hard Block / T4 Prohibited Check (`BLOCK`)
  2. Stage 2: Principal Restriction Check (`DENY`)
  3. Stage 3: Tool Restriction Check (`DENY`)
  4. Stage 4: Resource Scope Restriction Check (`DENY`)
  5. Stage 5: Risk Restriction Check (`REQUIRE_APPROVAL` / `DENY`)
  6. Stage 6: Explicit Approval Requirement Check (`REQUIRE_APPROVAL`)
  7. Stage 7: Explicit Allow Rule Check (`ALLOW`)
  8. Stage 8: Default-Deny Fallback (`DENY`)
- **Reason:** Milestone v2.9.0 Permission Engine requirement — guarantees that tool execution authorization is governed strictly by application code rather than LLM prompt obedience, system prompts, or natural language instructions. Establishes explicit permission identifiers (`filesystem.read`, `process.manage`, `system.control`, etc.), principal/user context, and fail-closed error handling across all execution entry points.
- **Alternatives considered:** Putting security authorization logic inside individual tools (rejected — violates separation of policy from tool implementation and creates duplicated, fragile security logic); relying on provider model system prompts (rejected — violates Core Security Principle: LLM models are not trusted to authorize themselves).
- **Trade-offs:** Adds ~280 lines of permission evaluation code in `backend/security/`, but guarantees non-bypassable security boundary.
- **Status:** Implemented in v2.9.0.

## D-022: Centralized Approval System & Pre-Execution Policy Revalidation Architecture

- **Decision:** Implement a centralized `ApprovalManager` (`backend/security/approval.py`), strongly-typed data models (`backend/security/approval_models.py`), SQLite persistence (`backend/storage/approval_store.py`), and explicit state machine (`ApprovalState`: `PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `CANCELLED`, `EXECUTED`). Wire `CentralToolExecutor` to enforce payload binding hash checks, single-use replay protection, and mandatory pre-execution policy revalidation (`APPROVAL + DENIED POLICY = DENIED`).
- **Reason:** Milestone v2.9.1 Approval System requirement — guarantees that actions requiring human authorization (`REQUIRE_APPROVAL`) create traceable, time-bound approval tickets that must be explicitly authorized by a human principal before tool execution. Pre-execution revalidation ensures that if security posture or policy changes between approval and execution, the updated policy remains authoritative and denies unauthorized actions. Secret argument redaction (`redact_sensitive_arguments`) prevents credential leaks in storage and API/CLI views.
- **Alternatives considered:** Making approvals permanent and non-expiring (rejected — violates time-bound security principle); allowing user approval to bypass updated `DENY` policies (rejected — violates Core Security Principle: An approval is NOT a permission); storing raw passwords/secrets in approval records (rejected — creates critical credential leakage vulnerability).
- **Trade-offs:** Adds SQLite store (`approvals.db`) and ~400 lines of state machine management code, but guarantees attributable, tamper-resistant human authorization.
- **Status:** Implemented in v2.9.1.

## Open / Deferred Items (not yet decided)




- **Gemini model version:** currently `gemini-3.5-flash`. A newer `gemini-3.6-flash` exists.
- **License choice (D-006):** MIT applied as a default: needs explicit owner sign-off.



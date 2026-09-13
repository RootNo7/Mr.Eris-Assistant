# ERIS — Changelog

Format: version, date, summary. Latest changes go at top.

## v2.9.1 (2026-09-06)

- Upgraded ERIS to **v2.9.1 — Approval System**:
  - Centralized Approval Manager: Created `ApprovalManager` (`backend/security/approval.py`) governing approval request creation, state transitions, expiration, and lifecycle decisions on top of the v2.9.0 Permission Engine.
  - Strongly-Typed Data Models: Created `backend/security/approval_models.py` defining `ApprovalRequest`, secret argument redaction (`redact_sensitive_arguments`), and payload binding hash calculation (`compute_binding_hash`).
  - Explicit State Machine: Added `ApprovalState` (`PENDING`, `APPROVED`, `REJECTED`, `EXPIRED`, `CANCELLED`, `EXECUTED`) and `ApprovalDecisionAction` enums in `backend/security/enums.py`. Strictly prevents illegal state transitions (terminal states cannot transition back to `PENDING` or `APPROVED`).
  - SQLite Persistence: Created `backend/storage/approval_store.py` managing persistent storage of approval requests in `backend/storage/approval/approvals.db` with thread-safe locks, database indices, and automatic expiration sweeping.
  - Pre-Execution Revalidation Protocol: Updated `CentralToolExecutor` (`backend/security/executor.py`) to mandate payload binding hash checks, single-use replay protection, and pre-execution policy revalidation (`APPROVAL + DENIED POLICY = DENIED`).
  - Deduplication Strategy: Automatically reuses existing active `PENDING` requests matching identical `binding_hash` and `session_id` to prevent pending request spam.
  - Secret Argument Redaction: Automatically replaces passwords, tokens, API keys, and credentials in arguments with `"<redacted>"` to protect sensitive values from log/storage leaks.
  - REST API & Schemas: Added approval schemas (`ApprovalRequestSchema`, `ApprovalListResponse`, `ApprovalActionRequest`, `ApprovalActionResponse`) in `backend/server/schemas.py`, engine delegates in `backend/server/service.py`, and REST endpoints (`GET /api/approvals/pending`, `GET /api/approvals/{id}`, `POST /api/approvals/{id}/approve`, `POST /api/approvals/{id}/reject`, `POST /api/approvals/{id}/cancel`) in `backend/server/app.py`.
  - CLI Integration: Added interactive CLI approval commands (`approvals`, `approve`, `reject`, `cancel`) in `apps/cli/main.py`.
  - Comprehensive Test Suite: Added 20+ new tests in `test_approval_system.py`, `test_approval_store.py`, `test_approval_revalidation.py`, and `test_approval_api.py` verifying state machine transitions, secret redaction, binding integrity, expiration, deduplication, policy change denials, argument mutation denials, replay protection, and REST API routes.
  - Version Discipline: Synchronized authoritative version `2.9.1` across `backend/core/version.py`, `pyproject.toml`, `test_version.py`, and documentation files.

## v2.9.0 (2026-09-06)

- Upgraded ERIS to **v2.9.0 — Permission Engine**:
  - Central Permission Engine Boundary: Created `backend/security/permissions.py` and `backend/security/engine.py` establishing a centralized authorization boundary implemented strictly in application code.
  - Decision Outcomes: Evaluates requests into strongly-typed `PermissionDecision` objects (`ALLOW`, `DENY`, `REQUIRE_APPROVAL`, `BLOCK`).
  - Standard Permission Identifiers: Defined standard permissions (`filesystem.read`, `filesystem.write`, `process.manage`, `network.access`, `system.control`, `system.admin`, `tool.execute`, `tool.read`).
  - Principal & Resource Context: Added `Principal` (identity, type, granted permissions) and `ResourceScope` (path prefixes, domain patterns, allowed/forbidden scope bounds) models.
  - Deterministic 8-Stage Evaluation Precedence: Enforces deterministic order (Stage 1: Global T4 Hard Block -> Stage 2: Principal Restriction -> Stage 3: Tool Restriction -> Stage 4: Resource Scope Restriction -> Stage 5: Risk Restriction -> Stage 6: Approval Threshold -> Stage 7: Explicit Allow -> Stage 8: Default Deny).
  - Strict Default-Deny & Fail-Closed Safety: Unmatched requests, unlisted tools, invalid policy parameters, or evaluation exceptions resolve safely to `DENY` or `BLOCK`.
  - Tool Security Metadata: Enhanced `BaseTool` and concrete tool implementations with `required_permission`, `enabled`, and `side_effect_level` attributes.
  - Chokepoint Integration: Refactored `PolicyEngine` (`backend/security/policy.py`) and `CentralToolExecutor` (`backend/security/executor.py`) to route all tool calls through `PermissionEngine`.
  - Security & Bypass Test Suite: Created `tests/unit/test_permission_engine.py` containing 20 tests verifying safe tools, unknown tools, T4 hard blocks, scope limits, signature mismatches, malformed policies, voice/API/CLI entry points, and direct execution bypass prevention.
  - Synchronized authoritative version `2.9.0` across `version.py`, `pyproject.toml`, and project documentation.

## v2.8.4 (2026-08-21)

- Upgraded ERIS to **v2.8.4 — Security & Runtime Stabilization**:
  - Priority 1: Approval Security — Updated `AutoApprovalGate` default to `default_approved=False` (deny-by-default). Enforced explicit approval requirement for T3 tools in `CentralToolExecutor` and `OrchestrationLoop`. Added `test_t3_tool_default_deny` regression test.
  - Priority 2: Secure Application Execution — Enforced strict application allowlisting in `launch_application` via `KNOWN_APP_MAP`. Replaced `shell=True` with `shell=False` process argument lists. Added security regression tests verifying rejection of arbitrary shell injection.
  - Priority 3: Tool Timeout & Cancellation Safety — Added `cancel()` method interface to `BaseTool` and process tracking in `RunPCCommandTool` to kill background processes on `TimeoutError` in `CentralToolExecutor`.
  - Priority 4: Production Voice Wiring — Created `create_production_voice_pipeline()` composition layer in `backend/voice/factory.py` and updated `apps/voice/main.py` to instantiate real production adapters (`SystemAudioSource`, `Pyttsx3TTSEngine`, `SystemAudioPlayer`, etc.) while keeping mocks injectable for testing.
  - Priority 5: Real TTS Audio Path — Updated `Pyttsx3TTSEngine` to generate real WAV audio bytes via pyttsx3 `save_to_file`, and updated `SystemAudioPlayer` to play WAV bytes via Windows `winsound.PlaySound`.
  - Priority 6: API Error Sanitization — Wrapped FastAPI exception routes in `backend/server/app.py` to return safe public error messages while preserving full diagnostic traces in `logger.error(..., exc_info=True)`. Added API error sanitization tests in `test_api.py`.
  - Priority 7: Test / Initialization Stability — Made `GeminiProvider` SDK initialization lazy so module imports and service instantiations do not require production secrets upfront. Updated `MockAudioSource` and test auth fixtures so full test suite collects and runs 100% offline.
  - Priority 8: Release Hygiene — Synchronized authoritative version `2.8.4` across `backend/core/version.py`, `pyproject.toml`, `requirements.txt`, and documentation files. Removed runtime storage files (`longterm_memory.db`, `session.json`, `audit.log`).

## v2.8.3 (2026-08-20)

- Upgraded ERIS Voice Subsystem to **v2.8.3 — Voice Personalization**:
  - `models.py`: Added `ResponseVerbosity` (`CONCISE`, `NORMAL`, `DETAILED`), `ResponseStyle` (`NEUTRAL`, `DIRECT`, `FRIENDLY`, `PROFESSIONAL`), `VoiceCapabilities`, and `VoiceProfile` dataclasses. Updated `VoiceConfig` to sync profile attributes seamlessly.
  - `profile.py`: Created `VoiceProfileManager` providing persistent JSON configuration (`backend/storage/settings/voice_profile.json`), bounds validation (speed `0.75`x to `1.5`x), enum validation, and corrupted config recovery.
  - `base.py`, `stt.py`, `tts.py`: Added `get_capabilities()` to STT/TTS engine interfaces and adapters. Added speaking speed rate adjustments to Mock and pyttsx3 TTS engines.
  - `pipeline.py`: Implemented quiet mode handling (skips TTS audio playback while preserving text response), pronunciation dictionary term overrides before synthesis, and profile context integration.
  - Server & REST API: Added Pydantic schemas in `backend/server/schemas.py`, voice profile delegates in `backend/server/service.py`, and REST endpoints (`GET/PUT /api/settings/voice`, `GET/POST /api/settings/voice/profiles`) in `backend/server/app.py`.
  - Voice Runner Daemon: Updated `apps/voice/main.py` CLI banner and active profile metadata display.
  - Unit Test Suite: Created `tests/unit/test_voice_personalization.py` (9 comprehensive unit tests covering models, bounds validation, persistence, corrupted config recovery, capability detection, quiet mode, pronunciation overrides, and REST settings API).
  - Recorded Decision D-020 in `docs/DECISIONS.md`.
  - Synchronized authoritative version `2.8.3` across `backend/core/version.py`, `pyproject.toml`, `tests/unit/test_version.py`, `README.md`, `PROJECT_STATE.md`, `ROADMAP.md`.

## v2.8.2 (2026-08-20)

- Upgraded ERIS Voice Subsystem to **v2.8.2 — Voice Reliability**:
  - `models.py`: Added `VoiceHealthState` enum (`HEALTHY`, `DEGRADED`, `FAILED`, `RECOVERING`), `VoiceTimeouts`, and `VoiceRetryConfig`.
  - `pipeline.py`: Added subsystem health tracking, strict 2-way stale result checking (`turn_id` + `generation_token`), explicit stage timeout guards, bounded retries with exponential backoff for transient failures, thread-safe playback locking, deterministic `reset_session()`, and `try...finally` resource cleanup wrappers.
  - Test Suite: Created `tests/unit/test_voice_reliability.py` (17 unit tests covering mic disconnection recovery, speaker failure, STT/TTS/provider error recovery, stale result protection, barge-in race condition safety, turn cancellation, session reset protocol, bounded retries, thread locking, and 50-turn long session stability).
  - Recorded Decision D-019 in `docs/DECISIONS.md`.
  - Synchronized version string `2.8.2`.


## v2.8.1 (2026-08-20)


- Upgraded ERIS Voice Subsystem to **v2.8.1 — Voice UX**:
  - `models.py`: Updated `VoiceState` enum with explicit states (`IDLE`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SPEAKING`, `INTERRUPTED`, `CANCELLED`, `PAUSED_FOR_APPROVAL`, `ERROR`). Added `VoiceTurnMetrics` dataclass. Expanded `VoiceConfig` with `input_device`, `output_device`, `interruption_enabled`, `streaming_enabled`, and `sentence_buffer_size`.
  - `pipeline.py`: Added deterministic state transition validator (`transition_to()`), UUID `turn_id` and atomic `generation_token` counter, barge-in `interrupt()`, atomic `cancel_turn()`, sentence-level TTS streaming output, user-friendly error output, and structured event logging.
- Voice Application Runner: Updated `apps/voice/main.py` CLI daemon runner with v2.8.1 banner, friendly error handling, and turn latency reporting.
- Test Suite: Updated `tests/unit/test_voice.py` to 18 unit tests covering models, mock audio stream, wake word, VAD, STT, TTS, player cancellation, state transitions, barge-in interruption, turn cancellation, sentence streaming, turn latency metrics, and permission integration.
- Fixed Gemini SDK Tool Declaration Parsing Bug: Removed internal `_guard` parameter from standalone function parameter signatures in `backend/tools/file_tools.py` using `**kwargs`. Eliminates complex class parsing errors (`PathGuard`) in `google-genai` SDK and prevents internal parameters from leaking into tool declarations across all AI providers.
- Fixed Provider Tool Name Alias Resolution: Enhanced `ToolRegistry` (`backend/tools/registry.py`) to build multi-alias resolution (`files.list`, `files_list`, `list_files`). Tools can now be retrieved and executed seamlessly regardless of whether a provider returns internal names with dots, OpenAI-sanitized names with underscores, or Python callable names.
- Fixed Session Boundary Bug — Stale History Repetition: Added `persist_across_sessions: bool = False` parameter to `ConversationBuffer` (`backend/ai/memory/buffer.py`). By default the conversation history buffer now starts **empty on every new ERIS process launch**. Old session conversation messages are no longer injected into new sessions, preventing ERIS from repeating previous paragraphs and getting stuck in voice loops. Long-term factual memory (`LongTermMemoryStore`) is unaffected and still persists.
- Recorded Decision D-018 in `docs/DECISIONS.md`.
- Synchronized version string `2.8.1` across `backend/core/version.py`, `pyproject.toml`, `tests/unit/test_version.py`, `README.md`, `docs/PROJECT_STATE.md`, `docs/ROADMAP.md`.


## v2.7.0 (2026-08-18)

- Implemented ERIS Modular Voice Interface Subsystem (`backend/voice/` & `apps/voice/`):
  - `models.py`: `VoiceState` (IDLE, LISTENING, TRANSCRIBING, PROCESSING, SPEAKING, PAUSED_FOR_APPROVAL, ERROR), `AudioChunk`, `TranscriptionResult`, `SynthesisResult`, `VoiceConfig`.
  - `base.py`: Hardware-decoupled Abstract Base Classes (`AudioSource`, `WakeWordDetector`, `VADEngine`, `STTEngine`, `TTSEngine`, `AudioPlayer`).
  - `audio.py`: Audio hardware adapters (`SystemAudioSource`, `MockAudioSource`, `SystemAudioPlayer`, `MockAudioPlayer`).
  - `wakeword.py`: `KeywordWakeWordDetector` (energy pulse pattern matcher) and `MockWakeWordDetector`.
  - `vad.py`: `EnergyVADEngine` (RMS amplitude calculator) and `MockVADEngine`.
  - `stt.py`: `FasterWhisperSTTEngine` (guarded local whisper adapter) and `MockSTTEngine`.
  - `tts.py`: `Pyttsx3TTSEngine` (guarded local synthesis adapter) and `MockTTSEngine`.
  - `pipeline.py`: `VoicePipeline` managing the state machine loop, silence timeouts, missing microphone degradation, STT/TTS error handling, interruption/cancellation via `threading.Event`, and security permission framework integration.
- Voice Application Runner: Implemented `apps/voice/main.py` CLI launcher (`python -m apps.voice.main` or `eris-voice`).
- Exception Taxonomy Extension: Added `VoiceError`, `AudioHardwareError`, `WakeWordError`, `STTError`, and `TTSError` to `backend/core/exceptions.py`.
- Security Framework Integration: Spoken high-risk commands pass through `ERISEngineService` and `CentralToolExecutor`, ensuring permission checks (T3/T4) and approval gates are strictly enforced.
- Unit Test Suite: Created `tests/unit/test_voice.py` (13 unit tests covering audio models, mock stream, wake word, VAD, STT, TTS, player cancellation, full cycle, empty speech filtering, missing mic handling, STT/TTS error handling, and high-risk action authorization).
- Version Bump: Updated authoritative version to `2.7.0` in `backend/core/version.py`, `pyproject.toml`.
- Recorded Decision D-017 in `docs/DECISIONS.md`.


- Implemented ERIS Controlled Single-Agent Orchestration Loop (`backend/orchestration/`):
  - `models.py`: `TaskStatus` (PENDING, RUNNING, WAITING_APPROVAL, COMPLETED, FAILED, CANCELLED, TIMED_OUT, LOOP_BREAKER), `StepStatus`, `ToolObservation`, `OrchestrationStep`, `OrchestrationTask`.
  - `config.py`: `OrchestrationConfig` enforcing hard safety governors (max_steps: 1-100, max_tool_calls: 1-200, max_seconds: 5-600, max_retries: 0-10).
  - `loop.py`: `OrchestrationLoop` executing think → act → observe iterations. Integrates sentinel-based tool intent parsing (`<<TOOL_CALL>>...<</TOOL_CALL>>`), governor checks before every step, automatic retries for transient errors, and cooperative `threading.Event` cancellation.
- Security Chokepoint Preservation: All tool invocations within the orchestration loop route through `ToolRegistry.execute_tool()` → `CentralToolExecutor` → `PolicyEngine` → `ApprovalGate` → `AuditLogger`. Security rules cannot be bypassed.
- Exception Taxonomy Extension: Added `OrchestrationError`, `OrchestrationTimeoutError`, `OrchestrationLoopBreakerError`, and `OrchestrationCancelledError` to `backend/core/exceptions.py`.
- Provider Abstraction Extension: Added optional `generate_step()` method to `AIProvider` (`backend/providers/base/provider.py`) with sentinel parsing fallback.
- Engine Service Integration: Added `process_orchestrated_chat()` to `ERISEngineService` (`backend/server/service.py`).
- API Server Endpoint: Added `POST /api/orchestrate` REST endpoint with auth guard and Pydantic schemas (`OrchestrationRequest`, `OrchestrationStepSchema`, `OrchestrationResponse`) in `backend/server/app.py` and `schemas.py`.
- Unit Test Suite: Created `tests/unit/test_orchestration.py` (15 unit tests covering single-step, multi-step, tool error recovery, repeated tool calls, timeout breaker, step count limit, tool call limit, approval gate authorization, cooperative cancellation, T4 security denial, config validation, and serialization).
- Version Bump: Updated authoritative version to `2.6.0` in `backend/core/version.py`, `pyproject.toml`.
- Recorded Decision D-016 in `docs/DECISIONS.md`.


- Implemented Secure Filesystem Tool Subsystem in `backend/tools/file_tools.py` (7 tools):
  - `files.list` (T0, `file.read`) — Lists directory entries within allowed roots.
  - `files.search` (T0, `file.read`) — Recursive filename search within allowed tree.
  - `files.read` (T1, `file.read`) — Reads text content of allowed files.
  - `files.write` (T2, `file.write`) — Writes/appends text to allowed files.
  - `files.create_directory` (T1, `file.write`) — Creates directories within allowed boundaries.
  - `files.copy` (T2, `file.write`) — Copies files within allowed boundaries.
  - `files.move` (T2, `file.write`) — Moves/renames files within allowed boundaries.
- Implemented `PathGuard` security module in `backend/security/path_guard.py`:
  - Explicit allowed filesystem roots (`ERIS_ALLOWED_FS_ROOTS`, default `os.getcwd()`).
  - Canonical path resolution via `os.path.realpath()` before all boundary checks.
  - Path traversal prevention (detects `../` and `..\` escape attempts).
  - Symlink escape protection (symlinks pointing outside allowed roots are blocked).
  - File size limit enforcement (`ERIS_MAX_FILE_SIZE_BYTES`, default 10 MB).
  - Dependency-injectable design (`PathGuard` accepted as tool constructor parameter).
- Added `PathSecurityError`, `PathTraversalError`, `UnauthorizedPathError`, `FileTooLargeError` to `backend/core/exceptions.py`.
- Added `ERIS_ALLOWED_FS_ROOTS` and `ERIS_MAX_FILE_SIZE_BYTES` settings to `Config`.
- Registered all 7 filesystem tools in `ERISEngineService` (`backend/server/service.py`) and CLI (`apps/cli/main.py`).
- Created unit test suite `tests/unit/test_file_tools.py` (11 tests: valid path, invalid path, traversal, symlink escape, nonexistent file, large file, read/write, list/search, copy/move, directory creation, unauthorized root).
- Fixed pre-existing test regression in `test_openrouter_provider.py` (now correctly expects `ProviderInitializationError`).
- Updated version to `2.5.2` across `version.py`, `pyproject.toml`, Web UI.
- Synchronized `README.md`, `ARCHITECTURE.md`, `DECISIONS.md`, `PROJECT_STATE.md`, `ROADMAP.md`.

## v2.5.0 (2026-08-18)

- Implemented ERIS Action Permission Framework in `backend/security/`:
  - `enums.py`: `RiskLevel` (T0–T4), `PolicyDecision`, `SecurityMode`, `ApprovalStatus`, `ExecutionStatus`.
  - `policy.py`: `PolicyEngine` evaluating security posture (`permissive`, `balanced`, `strict`), max auto-risk, and permission scopes.
  - `approval.py`: `ApprovalGate` abstract interface and `AutoApprovalGate` implementation.
  - `executor.py`: `CentralToolExecutor` chokepoint enforcing signature validation, risk policy evaluation, approval gating, timeout management (`ThreadPoolExecutor`), audit logging, and safe denial formatting.
  - `audit.py`: `AuditLogger` & `AuditEvent` writing structured JSON Lines records to `backend/storage/audit/audit.log`.
- Updated `BaseTool` (`backend/tools/base.py`) with risk metadata (`risk_level`, `requires_approval`, `timeout_seconds`, `permission_scope`).
- Annotated all tools (`SystemInfoTool`: T0, `LaunchAppTool`: T1, `OpenUrlTool`: T1, `RunPCCommandTool`: T3).
- Wired `ToolRegistry.execute_tool` through `CentralToolExecutor`.
- Added security settings to `Config` (`ERIS_SECURITY_MODE`, `ERIS_MAX_AUTO_RISK`, `ERIS_TOOL_TIMEOUT`).
- Created unit test suite `tests/unit/test_security_permission.py` (8 unit tests covering T0-T4 tools, denied policy, approval gates, validation, timeouts, and audit logging).
- Updated version to `2.5.0` across `version.py`, `pyproject.toml`, and Web UI.
- Documented D-014 decision in `docs/DECISIONS.md`.

## v2.4.1 (2026-08-18)

- Created single authoritative version module `backend/core/version.py` (`__version__ = "2.4.1"`).
- Created structured exception hierarchy in `backend/core/exceptions.py`.
- Refactored `Config` in `backend/core/config/settings.py`.
- Added `list_tools()` to `ToolRegistry`.

## v2.4.0 (2026-08-18)

- Implemented persistent SQLite long-term memory store (`LongTermMemoryStore`) and `MemoryExtractor`.

## v2.3.0

- Implemented configurable API Key authentication (`ERIS_AUTH_ENABLED` / `ERIS_API_KEY`) and Zero-Trust remote support.

## v2.2.0

- Built ChatGPT-style Web UI frontend (`apps/web`), live status polling, SSE client, and FastAPI static server mounting.

## v2.1.0

- Built FastAPI REST & SSE API server launcher (`apps/api/main.py`, `backend/server/app.py`).

## v0.1.10

- Implemented `LaunchAppTool`, `OpenUrlTool`, `RunPCCommandTool`, and `ToolRegistry` schema generators.

## v0.1.4

- Initial core architecture + provider abstraction (`AIProvider`, `GeminiProvider`, `Config`, CLI loop).

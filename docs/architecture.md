# ERIS — Architecture

Status: living document. Reflects what exists in code today (v2.8.3), plus planned extension points.

## 1. Current Layers (implemented)

```
apps/web/                  Interface Layer (ChatGPT-style Web UI: HTML5, CSS design system, SSE client)
apps/cli/main.py           Interface Layer (CLI with streaming output)
apps/api/main.py           Interface Layer (REST & SSE API server launcher)
apps/voice/main.py         Interface Layer (CLI launcher for ERIS Voice Assistant Daemon)
backend/voice/             Voice Subsystem (Modular Audio Pipeline, ABCs, Profile Manager, VoicePipeline)
  ├── models.py            VoiceState, VoiceHealthState, ResponseVerbosity, ResponseStyle, VoiceCapabilities, VoiceProfile, VoiceConfig
  ├── profile.py           VoiceProfileManager (persistent JSON storage, bounds validation, corrupted recovery)
  ├── base.py              Abstract Base Classes (AudioSource, WakeWordDetector, VADEngine, STTEngine, TTSEngine, AudioPlayer)
  ├── audio.py             SystemAudioSource, MockAudioSource, SystemAudioPlayer, MockAudioPlayer
  ├── wakeword.py          KeywordWakeWordDetector, MockWakeWordDetector
  ├── vad.py               EnergyVADEngine, MockVADEngine
  ├── stt.py               FasterWhisperSTTEngine, MockSTTEngine (with get_capabilities())
  ├── tts.py               Pyttsx3TTSEngine, MockTTSEngine (with get_capabilities(), speaking speed adjustment)
  └── pipeline.py          VoicePipeline (state machine, quiet mode, pronunciation dictionary overrides, profile context)
backend/server/            API Layer & Auth (FastAPI app, auth middleware, routes, schemas, voice settings REST APIs)
backend/orchestration/     Reasoning & Orchestration Layer (Controlled Single-Agent Loop, Governors, Task/Step Models)
  ├── models.py            TaskStatus, StepStatus, ToolObservation, OrchestrationStep, OrchestrationTask
  ├── config.py            OrchestrationConfig (max_steps, max_tool_calls, max_execution_seconds, max_retries)
  └── loop.py              OrchestrationLoop executing think → act → observe iterations
backend/security/          Permission & Security Policy Layer
  ├── enums.py             Risk levels (T0-T4), PolicyDecision (ALLOW, DENY, REQUIRE_APPROVAL, BLOCK), security modes
  ├── permissions.py       Permission identifiers, Principal, ResourceScope, PermissionRequest, PermissionContext, PermissionDecision
  ├── engine.py            PermissionEngine (8-stage evaluation precedence chain, default-deny, fail-closed handling)
  ├── policy.py            PolicyEngine adapter delegating to PermissionEngine
  ├── approval.py          ApprovalGate abstraction and AutoApprovalGate implementation
  ├── audit.py             AuditLogger writing JSON Lines to backend/storage/audit/audit.log
  ├── executor.py          CentralToolExecutor (mandatory security chokepoint passing all tools through PermissionEngine)
  └── path_guard.py        PathGuard enforcing allowed filesystem roots, traversal & symlink prevention
backend/core/version.py    Centralized authoritative version source (__version__ = "2.9.0")

backend/core/exceptions.py Structured ERIS exception hierarchy (ERISError, VoiceError, OrchestrationError, etc.)
backend/core/config/       Configuration — env-driven, security posture & filesystem guard settings
backend/core/logging/      Centralized logger factory
backend/providers/base/    AIProvider abstract interface with optional generate_step()
backend/providers/gemini/  Concrete Gemini implementation of AIProvider
backend/providers/ollama/  Concrete Ollama local implementation of AIProvider
backend/providers/openrouter/ Concrete OpenRouter gateway implementation of AIProvider
backend/tools/             Tool engine base (BaseTool with risk metadata) and ToolRegistry
  ├── system_info.py       SystemInfoTool (T0) — system information read
  ├── pc_tools.py          LaunchAppTool (T1), OpenUrlTool (T1), RunPCCommandTool (T3)
  └── file_tools.py        Secure Filesystem Subsystem — 7 tools guarded by PathGuard
backend/ai/memory/         ConversationBuffer + SQLite LongTermMemoryStore
tests/unit/                Unit tests for voice, orchestration, security, filesystem, version, exceptions, core, providers, tools, etc.
```

## 2. Action Permission Framework Pipeline

```
AI Provider (Gemini / OpenRouter / Ollama)
        ↓
    ToolRegistry.execute_tool(name, kwargs)
        ↓
    CentralToolExecutor (Single Mandatory Chokepoint)
        ├── 1. Argument & Signature Validation (inspect.signature)
        ├── 2. Risk & Policy Evaluation (PolicyEngine against RiskLevel T0-T4 & SecurityMode)
        ├── 3. Approval Gate Authorization (ApprovalGate check for T3/T4 / policy restrictions)
        ├── 4. Timeout-Guarded Execution (ThreadPoolExecutor with timeout_seconds)
        ├── 5. Audit Logging (AuditLogger writing JSON Lines to backend/storage/audit/audit.log)
        └── 6. Safe Response Format (returns clean result or [SECURITY DENIAL] string)
```

## 3. Secure Filesystem Pipeline (v2.5.2)

```
AI Provider requests file operation
        ↓
    ToolRegistry.execute_tool("files.*", kwargs)
        ↓
    CentralToolExecutor (risk policy + approval gate)
        ↓
    PathGuard.validate_path(path)
        ├── os.path.realpath() — canonicalize path
        ├── is_within_root() — boundary check against allowed_roots
        ├── Traversal detection ("../" in path_input)
        ├── Symlink escape check (os.path.islink → realpath → boundary check)
        └── validate_file_size() — reject if > ERIS_MAX_FILE_SIZE_BYTES
        ↓
    Filesystem Operation (read/write/copy/move/list/search/mkdir)
        ↓
    AuditLogger (write/copy/move operations logged)
```

## 4. Tool Risk Classification Taxonomy

| Risk Level | Type | Examples | Auto-Allowed (Balanced) |
|---|---|---|---|
| T0 | Read-Only / Zero Risk | `get_system_info`, `files.list`, `files.search` | ✅ Always |
| T1 | Low Risk / Reversible | `files.read`, `files.create_directory`, `launch_application`, `open_url` | ✅ Yes |
| T2 | Medium Risk / State Change | `files.write`, `files.copy`, `files.move` | ✅ Yes |
| T3 | High Risk / Destructive | `execute_pc_command` | ❌ Requires Approval |
| T4 | Critical Risk / Unsafe | System admin operations | ❌ Always Denied |

## 5. Filesystem Tool Inventory

| Tool | Risk | Scope | Description |
|---|---|---|---|
| `files.list` | T0 | `file.read` | Lists entries within an allowed directory |
| `files.search` | T0 | `file.read` | Recursive filename search within allowed tree |
| `files.read` | T1 | `file.read` | Reads text content of an allowed file |
| `files.write` | T2 | `file.write` | Writes or appends content to an allowed file |
| `files.create_directory` | T1 | `file.write` | Creates a directory within allowed boundaries |
| `files.copy` | T2 | `file.write` | Copies a file within allowed boundaries |
| `files.move` | T2 | `file.write` | Moves or renames within allowed boundaries |

## 6. PathGuard Security Model

`PathGuard` is the exclusive gatekeeper for all filesystem operations. It enforces:

1. **Explicit Allowed Roots** — only paths within `ERIS_ALLOWED_FS_ROOTS` (default: `os.getcwd()`) pass.
2. **Canonical Path Resolution** — `os.path.realpath()` resolves all `.`, `..`, and symlinks before boundary checking.
3. **Traversal Prevention** — relative traversal patterns in path input trigger `PathTraversalError`.
4. **Symlink Escape Guard** — symlinks pointing outside allowed roots trigger `PathTraversalError`.
5. **File Size Limits** — read/write operations validate against `ERIS_MAX_FILE_SIZE_BYTES` (default 10 MB).
6. **Dependency Injection** — tools accept `PathGuard` as a constructor parameter, enabling safe scoped testing.

## 7. Full Target Layering (from the ERIS Operating Manual)

```
ERIS
├── Interface Layer          IMPLEMENTED (Web UI, REST/SSE API, CLI, Voice CLI)
├── Conversation Layer        IMPLEMENTED (session buffer + system persona)
├── Reasoning / Orchestration  IMPLEMENTED (Controlled single-agent OrchestrationLoop + safety governors)
├── Memory Layer              IMPLEMENTED (Session Buffer + SQLite Long-Term)
├── Provider Abstraction       IMPLEMENTED (Gemini, OpenRouter, Ollama)
├── Tool Layer                 IMPLEMENTED (PC tools, system info, secure filesystem tools)
├── Permission / Security      IMPLEMENTED (CentralToolExecutor, PolicyEngine, PathGuard, AuditLogger)
├── Voice Subsystem            IMPLEMENTED (VoicePipeline, Wake Word, VAD, STT, TTS, Speaker)
├── Automation Layer           NOT IMPLEMENTED
├── Plugin Layer               NOT IMPLEMENTED
├── Integration Layer          NOT IMPLEMENTED
└── Infrastructure Layer       PARTIAL (config + version + exceptions + logging)
```

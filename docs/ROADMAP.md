# ERIS — Roadmap

Roadmap evolves based on actual progress. Candidate milestones are evaluated one at a time.

## Completed Milestones

| Milestone | Key Accomplishments | Status |
|---|---|---|
| **v0.1.x** | Core repo layout, `AIProvider` ABC, Gemini provider, CLI loop, env config | Done |
| **v0.1.9** | OpenRouter multi-model API gateway provider integration | Done |
| **v0.1.10** | PC Tool Engine (`LaunchAppTool`, `OpenUrlTool`, `RunPCCommandTool`), ToolRegistry, function schemas | Done |
| **v2.1.0** | FastAPI REST & SSE API server (`/api/health`, `/api/providers`, `/api/tools`, `/api/chat/stream`) | Done |
| **v2.2.0** | ChatGPT-style Web UI frontend (`apps/web`), live status polling, SSE client, static server mounting | Done |
| **v2.3.0** | Bearer API token security (`ERIS_AUTH_ENABLED` / `ERIS_API_KEY`) & Zero-Trust remote support | Done |
| **v2.4.0** | Persistent SQLite Long-Term Memory (`LongTermMemoryStore`), `MemoryExtractor`, Web UI Facts Inspector | Done |
| **v2.4.1** | Centralized version source (`backend/core/version.py`), ERIS Exception Taxonomy, Config cleanup, ToolRegistry completion | Done |
| **v2.5.0** | Action Permission Framework (`CentralToolExecutor`, `PolicyEngine`, `RiskLevel` T0-T4, `ApprovalGate`, `AuditLogger`) | Done |
| **v2.5.2** | Secure Filesystem Tool Subsystem (`PathGuard`, 7 guarded filesystem tools) | Done |
| **v2.6.0** | Controlled Single-Agent Orchestration Loop (`OrchestrationLoop`, `OrchestrationConfig`, 3 safety governors, `POST /api/orchestrate`) | Done |
| **v2.7.0** | Modular Voice Interface Subsystem (`VoicePipeline`, Wake Word, VAD, STT, TTS, Speaker, `apps/voice/main.py`) | Done |
| **v2.8.1** | Voice UX Release (Deterministic State Machine, Turn Tokens, Barge-in Interruption, Cancellation, Sentence Streaming, Latency Metrics) | Done |
| **v2.8.2** | Voice Reliability Release (Subsystem Health Tracking, Stale Result Protection, Timeout Guards, Bounded Retries, Session Reset Protocol) | Done |
| **v2.8.3** | Voice Personalization Release (Voice Profiles, Speed 0.75x-1.5x, Verbosity, Response Style, Quiet Mode, Pronunciation Overrides, REST APIs) | Done |
| **v2.8.4** | Security & Runtime Stabilization (Deny-by-default approval gate, strict app allowlisting, timeout cancellation, real pyttsx3 TTS audio synthesis, sanitized API errors) | Done |
| **v2.9.0** | Permission Engine (Central authorization boundary in application code, 8-stage precedence chain, explicit permissions, Principal context, default-deny, fail-closed handling) | Done |
| **v2.9.1** | Approval System (Centralized ApprovalManager, SQLite storage, payload binding hash, single-use replay protection, pre-execution policy revalidation, secret redaction, REST API & CLI) | Done |

## Current Stage: v2.9.1 Completed — Approval System Release

**Status:** The Approval System (v2.9.1) is officially complete.

## Next Stage: Audit & Kill Switch (v2.9.2)

- **v2.9.2 — Audit + Kill Switch:** Comprehensive audit event logging, action telemetry, and instant panic emergency shutdown capabilities.


## Future Candidates (v2.6+)

Per manual §68, candidate milestones are evaluated one at a time:

- **Voice Interface Layer** (STT/TTS, wake-word, voice response)
- **Multimodal Vision Layer** (Screen understanding, image analysis, OCR)
- **Plugin System** (Isolated integrations for third-party services)
- **Advanced Reasoning / Task Orchestrator** (Task decomposition, multi-tool coordination)

## Hard Prerequisites Before Advanced Automation

- **Computer control, external automation, and plugins** require a proven **Action Permission Framework** (Completed in v2.5.0).
- **Autonomous orchestration behavior** must not be built before both the permission framework and testing harness are verified.

## Out of Scope For Now

- Gaming agents / capabilities
- Business/content-creation modules
- Multi-user identity management

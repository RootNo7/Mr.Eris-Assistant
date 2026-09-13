# ERIS — Testing

## How to run

```bash
pip install -e ".[dev]"
pytest
```

## Current coverage

134 passed, 1 skipped across 17 test modules:
- `test_action_permission_framework.py` — Action Permission Framework, risk levels T0-T4, PolicyEngine, ApprovalGate, AuditLogger.
- `test_ai_provider.py` & `test_gemini_provider.py` & `test_openrouter_provider.py` & `test_ollama_provider.py` — Provider abstraction & adapters.
- `test_audit.py` — Audit log structured JSON Lines events.
- `test_file_tools.py` — Secure Filesystem Subsystem (7 tools, PathGuard security traversal protection).
- `test_filesystem_guard.py` — Allowed roots, size limits, symlink escape checks.
- `test_memory.py` — Conversation memory buffer & SQLite long-term fact storage.
- `test_orchestration_loop.py` — Single-Agent Orchestration Loop with safety governors.
- `test_policy.py` & `test_tool_registry.py` & `test_tools.py` — Security policies, tool registry, tool resolution aliases.
- `test_version.py` — Authoritative version checks (`2.8.3`).
- `test_voice.py` — Modular Voice UX Subsystem (18 unit tests).
- `test_voice_reliability.py` — Voice Reliability & Resilience (17 unit tests).
- `test_voice_personalization.py` — Voice Personalization (9 unit tests: models, bounds validation, profile manager persistence, corrupted config recovery, provider capabilities, quiet mode, pronunciation overrides, and REST settings APIs).

All unit tests run 100% offline using hardware-decoupled mock components.


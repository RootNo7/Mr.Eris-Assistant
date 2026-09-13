# ERIS — Evolutionary Responsive Intelligence System

A modular, provider-agnostic personal AI digital intelligence system.

## Status

**v2.8.4** — Security & Runtime Stabilization.
Focuses on platform security hardening and runtime stabilization: deny-by-default approval gating (`AutoApprovalGate(default_approved=False)`), strict desktop application allowlisting (`KNOWN_APP_MAP`) with `shell=False` execution, process cancellation and timeout safety (`BaseTool.cancel()`), production voice composition wiring (`create_production_voice_pipeline`), real pyttsx3 WAV audio synthesis and Windows `winsound.PlaySound` playback, API error message sanitization, resilient lazy SDK initialization for offline test stability, and source release hygiene.



## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pip install -r requirements.txt
cp .env.example .env               # Fill in your GEMINI_API_KEY / OPENROUTER_API_KEY
```

## Run

### CLI Interface
```bash
python -m apps.cli.main
```

### API Server & Web UI
```bash
python -m apps.api.main
```
Then open `http://localhost:8000` in your browser.

## Test

```bash
python -m pytest
```

## Project Structure

```
apps/
├── api/             REST & SSE API launcher (FastAPI)
├── cli/             Terminal conversation loop with ANSI styling
└── web/             ChatGPT-style HTML5/CSS Web UI frontend
backend/
├── ai/              Conversation history buffer & SQLite long-term memory store
├── core/            Authoritative version, structured exceptions, config, & logging
├── providers/       AIProvider interface & implementations (Gemini, OpenRouter, Ollama)
├── security/        Action Permission Framework (enums, PolicyEngine, ApprovalGate, AuditLogger, CentralToolExecutor)
├── server/          FastAPI endpoints, authorization middleware, & schemas
└── tools/           BaseTool with risk metadata, ToolRegistry, PC automation tools, & SystemInfo tool
docs/                Architecture documentation, decision log, roadmap, & state
tests/
└── unit/            Comprehensive unit test suite
```

## Security

- Security policies are strictly enforced in **executable application code** (`CentralToolExecutor`), never relying solely on system prompts or LLM instructions.
- Central Chokepoint validates tool parameters, evaluates risk policy, requires approval for sensitive actions (T3/T4), enforces execution timeouts, and records structured audit events.
- Real secrets live only in `.env`, which is git-ignored. `.env.example` contains placeholder values only.
- Configurable Bearer API token security (`ERIS_AUTH_ENABLED=true` and `ERIS_API_KEY`) protects endpoints when exposed over local networks or Zero-Trust remote tunnels (Tailscale / Cloudflare Tunnel).

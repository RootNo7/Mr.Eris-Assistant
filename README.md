Architecture

«Project: ERIS (Evolutionary Responsive Intelligent System)
Version: v1 Foundation
Status: Active Development»

---

Overview

ERIS is designed as a modular, provider-agnostic Personal AI Operating System. Rather than building features around a specific AI model, ERIS separates intelligence providers from the core application through a clean abstraction layer.

The objective of v1 is to establish a stable architectural foundation that future versions can extend without major redesign.

---

Design Principles

The architecture is guided by the following principles:

- Foundation First — prioritize a stable core before advanced capabilities.
- Separation of Concerns — each module has a single responsibility.
- Provider Independence — application logic must never depend on a specific AI provider.
- Modularity — components should be independently replaceable and testable.
- Incremental Evolution — extend the system instead of rewriting it.

---

System Architecture

User
  │
  ▼
Frontend
  │
  ▼
FastAPI API
  │
  ▼
Conversation Engine
  │
  ▼
Provider Manager
  │
  ▼
AI Provider Interface
  │
  ▼
Google Gemini

Application logic communicates only with the Provider Manager, allowing AI providers to be replaced or expanded without affecting the rest of the system.

---

Repository Structure

ERIS/
├── backend/
│   ├── api/
│   ├── ai/
│   ├── core/
│   ├── providers/
│   ├── services/
│   ├── models/
│   └── tests/
├── frontend/
├── docs/
├── configs/
├── scripts/
└── tests/

Each directory represents a distinct architectural responsibility and should remain loosely coupled.

---

Core Components

Component| Responsibility
Frontend| User interface and client-side interactions
API| HTTP endpoints, request validation, response handling
Conversation Engine| Session management and dialogue orchestration
Provider Layer| AI provider abstraction and integrations
Core| Configuration, logging, exceptions, shared utilities

---

AI Provider Architecture

ERIS uses a provider abstraction layer to isolate model-specific implementations.

Application
      │
      ▼
Provider Manager
      │
      ▼
Provider Interface
      │
      ▼
Gemini Provider

Google Gemini is the initial provider for v1.

Future providers such as OpenAI, Anthropic, Ollama, llama.cpp, and other local or cloud models will implement the same interface.

---

Current Scope (v1)

The current version focuses on establishing the foundation:

- Modular project structure
- Configuration system
- Logging and error handling
- Provider abstraction
- Google Gemini integration
- Conversation engine
- FastAPI backend
- Web frontend
- Documentation
- Initial testing

Advanced capabilities are intentionally deferred until the foundation is stable.

---

Future Roadmap

Version| Focus
v1| Foundation and Gemini integration
v2| Persistent memory, tools, local AI support
v3| Voice, vision, plugins, richer interaction
v4| Automation, device integration, multi-agent workflows
v5+| Long-term platform evolution and future AI capabilities

Each version builds on the existing architecture without unnecessary rewrites.

---

Engineering Standards

All new modules should be:

- Modular
- Documented
- Testable
- Loosely coupled
- Secure by default
- Easy to maintain

Architecture should evolve through extension rather than replacement.

---

Architecture Decisions

Significant architectural decisions should be documented as Architecture Decision Records (ADRs) under:

docs/decisions/

Each ADR should explain:

- The problem
- The decision
- Alternatives considered
- Rationale
- Consequences

---

Success Criteria

ERIS v1 is considered complete when it provides a stable, maintainable, and provider-agnostic foundation with Google Gemini integrated through the provider abstraction layer.

The success of v1 is measured by the quality of its architecture—not by the number of implemented features.
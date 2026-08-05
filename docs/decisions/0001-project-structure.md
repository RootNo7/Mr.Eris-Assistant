# ADR 0001: Adopt Monorepo Directory Layout with Presentation and Kernel Isolation

## Status
Accepted

## Context
[cite_start]Previous ERIS iterations suffered from tight coupling between UI components (PyQt) and AI provider SDKs, accumulating technical debt and making testing difficult. We need a structure that allows multiple frontends (Desktop, CLI, Web) to use the exact same backend engine without code modification.

## Decision
We adopt a monorepo layout separating `apps/` (Presentation) from `backend/` (Core Kernel & Services) [cite: 107-109, 115]. [cite_start]The backend will expose clear interfaces, treat LLMs as replaceable providers, and place tests at the project root (`tests/`) to ensure clean packaging.

## Consequences
### Positive
- UI components can be rewritten or replaced without touching core AI logic.
- Providers can be added under `backend/providers/` by extending standard interfaces.
- Architecture rationale is preserved for long-term maintainability [cite: 110-112].

### Negative / Trade-offs
- Slightly higher initial setup complexity compared to single-folder projects.

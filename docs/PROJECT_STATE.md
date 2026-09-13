# ERIS — Project State

Update this file at the end of meaningful development sessions so future
sessions (any assistant, any machine) can recover context fast.

---

**Current Version:** v2.9.1

**Current Objective:** ERIS v2.9.1 Approval System — Establishing a centralized, stateful human authorization mechanism on top of the v2.9.0 Permission Engine. Supports explicit approval request lifecycles (PENDING, APPROVED, REJECTED, EXPIRED, CANCELLED, EXECUTED), payload binding hashes, single-use replay protection, pre-execution policy revalidation (APPROVAL + DENIED POLICY = DENIED), secret redaction, SQLite persistence, deduplication, REST API endpoints, and CLI commands.

**Completed:**
- Milestone v2.8.0 — Voice Foundation
- Milestone v2.8.1 — Voice UX
- Milestone v2.8.2 — Voice Reliability
- Milestone v2.8.3 — Voice Personalization
- Milestone v2.8.4 — Security & Runtime Stabilization
- Milestone v2.9.0 — Permission Engine
- Milestone v2.9.1 — Approval System:
  - Created `backend/security/approval_models.py` defining `ApprovalRequest`, secret argument redaction (`redact_sensitive_arguments`), and payload binding hash calculation (`compute_binding_hash`).
  - Added `ApprovalState` and `ApprovalDecisionAction` enums in `backend/security/enums.py`.
  - Created `backend/storage/approval_store.py` providing SQLite-backed persistence (`approvals.db`), state transition updates, thread-safe locks, and auto-expiration.
  - Implemented `ApprovalManager` in `backend/security/approval.py` for state machine validation, deduplication, and lifecycle decisions.
  - Updated `CentralToolExecutor` in `backend/security/executor.py` with mandatory pre-execution policy revalidation, payload binding hash checks, and single-use replay protection.
  - Created API schemas in `backend/server/schemas.py`, service integration in `backend/server/service.py`, and FastAPI endpoints (`/api/approvals/...`) in `backend/server/app.py`.
  - Added interactive CLI approval commands (`approvals`, `approve`, `reject`, `cancel`) in `apps/cli/main.py`.
  - Created 20+ unit and security tests in `test_approval_system.py`, `test_approval_store.py`, `test_approval_revalidation.py`, and `test_approval_api.py`.
  - Synchronized version `2.9.1` across `version.py`, `pyproject.toml`, and project documentation.
  - **Test bug-fix pass (post-implementation):** Corrected 6 issues discovered during full-suite verification:
    1. `test_approval_replay_protection` — assertion strings did not match actual denial message format (`"executed" in state` not `"replay blocked"`).
    2. `test_expired_approval_execution_denial` — `TTL=0.1 s` caused `list_pending()` → `mark_expired()` to sweep the request before ID could be read (`IndexError`); fixed by using `TTL=1.0 s`, capturing ID directly from `create_request()`, approving before sleeping, then sleeping past TTL.
    3–4. `test_api_approvals_workflow` / `test_api_approval_not_found` — tests sent `X-API-Key` header but `auth.py` requires `X-ERIS-API-Key`; fixed by applying `monkeypatch.setenv("ERIS_AUTH_ENABLED", "false")` (established project pattern).
    5. `test_t3_tool_default_deny` — pre-v2.9.1 test expected `[SECURITY DENIAL]` for T3 tools; Approval System now returns `[SECURITY APPROVAL REQUIRED]` with a pending request; test updated accordingly.
    6. `backend/server/schemas.py` — `ApprovalRequestSchema.arguments: Dict[str, Any]` used `Any` which was missing from the `typing` import, causing Pydantic `TypeAdapter` `class-not-fully-defined` at runtime; fixed by adding `Any` to the import.

**In Progress:**
- Milestone v2.9.1 Approval System complete.

**Known Bugs:**
- None.

**Tests:**
- 171+ pytest unit, API, state-machine, and security tests passing 100% offline.

**Next Step:**
- Proceed to v2.9.2 — Audit + Kill Switch (Structured security event logging and emergency system shutdown boundaries).

**Architectural Decisions:** See `DECISIONS.md` (D-001 through D-022).

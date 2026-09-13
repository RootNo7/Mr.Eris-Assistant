import os
import json
import sqlite3
import threading
import time
from typing import List, Optional, Dict, Any
from backend.security.enums import RiskLevel, ApprovalState
from backend.security.approval_models import ApprovalRequest
from backend.core.logging.logger import logger


class ApprovalStore:
    """
    SQLite-backed thread-safe persistent store for ERIS Approval Requests (v2.9.1).
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = os.path.join(os.getcwd(), "backend", "storage", "approval")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "approvals.db")

        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes approval requests table and indices."""
        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS approval_requests (
                        approval_id TEXT PRIMARY KEY,
                        request_id TEXT NOT NULL,
                        session_id TEXT,
                        principal_id TEXT NOT NULL,
                        tool_name TEXT NOT NULL,
                        action TEXT NOT NULL,
                        arguments_json TEXT NOT NULL,
                        raw_arguments_hash TEXT NOT NULL,
                        resource_scope TEXT NOT NULL,
                        permission TEXT NOT NULL,
                        risk_level INTEGER NOT NULL,
                        reason TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        state TEXT NOT NULL,
                        decided_at REAL,
                        decided_by TEXT,
                        binding_hash TEXT NOT NULL,
                        used INTEGER NOT NULL DEFAULT 0
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_state ON approval_requests(state)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_session ON approval_requests(session_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_binding ON approval_requests(binding_hash)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_approval_expires ON approval_requests(expires_at)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite ApprovalStore DB: {e}")
            raise

    def store_request(self, req: ApprovalRequest) -> None:
        """Stores a new approval request in the database."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO approval_requests (
                    approval_id, request_id, session_id, principal_id, tool_name, action,
                    arguments_json, raw_arguments_hash, resource_scope, permission,
                    risk_level, reason, created_at, expires_at, state, decided_at,
                    decided_by, binding_hash, used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                req.approval_id,
                req.request_id,
                req.session_id,
                req.principal_id,
                req.tool_name,
                req.action,
                json.dumps(req.arguments),
                req.raw_arguments_hash,
                req.resource_scope,
                req.permission,
                int(req.risk_level),
                req.reason,
                req.created_at,
                req.expires_at,
                req.state.value if isinstance(req.state, ApprovalState) else str(req.state),
                req.decided_at,
                req.decided_by,
                req.binding_hash,
                1 if req.used else 0
            ))
            conn.commit()

    def _row_to_request(self, row: sqlite3.Row) -> ApprovalRequest:
        try:
            args = json.loads(row["arguments_json"])
        except Exception:
            args = {}
        
        return ApprovalRequest(
            approval_id=row["approval_id"],
            request_id=row["request_id"],
            session_id=row["session_id"],
            principal_id=row["principal_id"],
            tool_name=row["tool_name"],
            action=row["action"],
            arguments=args,
            raw_arguments_hash=row["raw_arguments_hash"],
            resource_scope=row["resource_scope"],
            permission=row["permission"],
            risk_level=RiskLevel(row["risk_level"]),
            reason=row["reason"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            state=ApprovalState(row["state"]),
            decided_at=row["decided_at"],
            decided_by=row["decided_by"],
            binding_hash=row["binding_hash"],
            used=bool(row["used"])
        )

    def get_request(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Retrieve an approval request by approval_id."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approval_requests WHERE approval_id = ?", (approval_id,))
            row = cursor.fetchone()
            if row:
                return self._row_to_request(row)
            return None

    def find_active_pending(self, binding_hash: str, session_id: Optional[str] = None) -> Optional[ApprovalRequest]:
        """
        Finds an unexpired PENDING approval request matching binding_hash and session_id.
        Used for request deduplication.
        """
        now = time.time()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    "SELECT * FROM approval_requests WHERE binding_hash = ? AND session_id = ? AND state = 'pending' AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                    (binding_hash, session_id, now)
                )
            else:
                cursor.execute(
                    "SELECT * FROM approval_requests WHERE binding_hash = ? AND state = 'pending' AND expires_at > ? ORDER BY created_at DESC LIMIT 1",
                    (binding_hash, now)
                )
            row = cursor.fetchone()
            if row:
                return self._row_to_request(row)
            return None

    def list_pending(self, session_id: Optional[str] = None) -> List[ApprovalRequest]:
        """Lists all active (unexpired) PENDING approval requests."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if session_id:
                cursor.execute(
                    "SELECT * FROM approval_requests WHERE state = 'pending' AND session_id = ? AND expires_at > ? ORDER BY created_at DESC",
                    (session_id, now)
                )
            else:
                cursor.execute(
                    "SELECT * FROM approval_requests WHERE state = 'pending' AND expires_at > ? ORDER BY created_at DESC",
                    (now,)
                )
            rows = cursor.fetchall()
            return [self._row_to_request(row) for row in rows]

    def list_all(self, limit: int = 100) -> List[ApprovalRequest]:
        """Lists all approval requests ordered by created_at DESC."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM approval_requests ORDER BY created_at DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            return [self._row_to_request(row) for row in rows]

    def update_state(
        self,
        approval_id: str,
        new_state: ApprovalState,
        decided_by: Optional[str] = None,
        decided_at: Optional[float] = None,
        mark_used: bool = False
    ) -> bool:
        """Atomically updates the state of an approval request."""
        now = decided_at or time.time()
        state_str = new_state.value if isinstance(new_state, ApprovalState) else str(new_state)
        
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            if mark_used:
                cursor.execute("""
                    UPDATE approval_requests
                    SET state = ?, decided_by = COALESCE(?, decided_by), decided_at = COALESCE(?, decided_at), used = 1
                    WHERE approval_id = ?
                """, (state_str, decided_by, now, approval_id))
            else:
                cursor.execute("""
                    UPDATE approval_requests
                    SET state = ?, decided_by = COALESCE(?, decided_by), decided_at = COALESCE(?, decided_at)
                    WHERE approval_id = ?
                """, (state_str, decided_by, now, approval_id))
            conn.commit()
            return cursor.rowcount > 0

    def mark_expired(self) -> int:
        """Transitions any PENDING approval requests whose expires_at <= current time to EXPIRED."""
        now = time.time()
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE approval_requests
                SET state = 'expired'
                WHERE state = 'pending' AND expires_at <= ?
            """, (now,))
            conn.commit()
            return cursor.rowcount

    def clear(self) -> None:
        """Wipes table contents (used in unit tests)."""
        with self._lock, self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM approval_requests")
            conn.commit()

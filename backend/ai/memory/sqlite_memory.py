import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from backend.core.logging.logger import logger

class LongTermMemoryStore:
    """
    SQLite-backed persistent long-term memory store for ERIS.
    Stores user facts, preferences, project details, and system memories.
    """

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_dir = os.path.join(os.getcwd(), "backend", "storage", "memory")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "longterm_memory.db")

        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Creates facts table and indexes if they do not exist."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS facts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        category TEXT NOT NULL DEFAULT 'general',
                        key TEXT NOT NULL UNIQUE,
                        value TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_facts_key ON facts(key)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category)
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite long-term memory DB: {e}")
            raise

    def store_fact(self, key: str, value: str, category: str = "general") -> Dict[str, Any]:
        """
        Stores or updates a long-term fact key/value pair.
        """
        now = datetime.now(timezone.utc).isoformat()
        key_clean = key.strip().lower().replace(" ", "_")
        value_clean = value.strip()

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO facts (category, key, value, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        category = excluded.category,
                        value = excluded.value,
                        updated_at = excluded.updated_at
                """, (category, key_clean, value_clean, now, now))
                conn.commit()

            logger.info(f"Stored long-term memory fact: [{key_clean}] -> '{value_clean}'")
            return self.get_fact(key_clean)
        except Exception as e:
            logger.error(f"Failed to store fact [{key}]: {e}")
            raise

    def get_fact(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieves a specific fact by key."""
        key_clean = key.strip().lower().replace(" ", "_")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM facts WHERE key = ?", (key_clean,))
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve fact [{key}]: {e}")
            return None

    def get_all_facts(self) -> List[Dict[str, Any]]:
        """Retrieves all stored long-term facts ordered by update time."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM facts ORDER BY updated_at DESC")
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list long-term facts: {e}")
            return []

    def search_facts(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches facts using keyword matching across key, value, and category.
        """
        query_words = [w.strip().lower() for w in query.split() if len(w.strip()) > 2]
        if not query_words:
            return self.get_all_facts()[:5]

        matched_facts = []
        all_facts = self.get_all_facts()

        for fact in all_facts:
            combined_text = f"{fact['category']} {fact['key']} {fact['value']}".lower()
            score = sum(1 for word in query_words if word in combined_text)
            if score > 0:
                matched_facts.append((score, fact))

        matched_facts.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in matched_facts]

    def delete_fact(self, key: str) -> bool:
        """Deletes a fact by key."""
        key_clean = key.strip().lower().replace(" ", "_")
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM facts WHERE key = ?", (key_clean,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete fact [{key}]: {e}")
            return False

    def clear_all_facts(self) -> None:
        """Wipes all long-term memory facts."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM facts")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to clear long-term memory facts: {e}")

    def format_recalled_facts_context(self, prompt: str, max_facts: int = 5) -> str:
        """
        Formats relevant facts into a structured system context injection string.
        """
        relevant_facts = self.search_facts(prompt)
        if not relevant_facts:
            return ""

        facts_to_include = relevant_facts[:max_facts]
        formatted_lines = [f"- {f['key'].replace('_', ' ').title()}: {f['value']}" for f in facts_to_include]
        
        return (
            "\n[RECALLED LONG-TERM MEMORY FACTS]\n"
            + "\n".join(formatted_lines)
            + "\n[END RECALLED MEMORY]\n\n"
        )

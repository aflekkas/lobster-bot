import sqlite3
import time
from pathlib import Path


class SessionManager:
    def __init__(self, db_path: Path):
        self._db = sqlite3.connect(str(db_path))
        self._db.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                chat_id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS session_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                archived_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                cost_usd REAL NOT NULL DEFAULT 0,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS chat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_chat_log_chat_id ON chat_log(chat_id);
            CREATE INDEX IF NOT EXISTS idx_chat_log_timestamp ON chat_log(timestamp);
        """)

    def get_session(self, chat_id: int) -> str | None:
        row = self._db.execute(
            "SELECT session_id FROM sessions WHERE chat_id = ?", (chat_id,)
        ).fetchone()
        return row["session_id"] if row else None

    def set_session(self, chat_id: int, session_id: str):
        now = time.time()
        self._db.execute(
            """INSERT INTO sessions (chat_id, session_id, created_at, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(chat_id)
               DO UPDATE SET session_id = excluded.session_id, updated_at = excluded.updated_at""",
            (chat_id, session_id, now, now),
        )
        self._db.commit()

    def clear_session(self, chat_id: int):
        self._db.execute("DELETE FROM sessions WHERE chat_id = ?", (chat_id,))
        self._db.commit()

    def touch_session(self, chat_id: int):
        self._db.execute(
            "UPDATE sessions SET updated_at = ? WHERE chat_id = ?",
            (time.time(), chat_id),
        )
        self._db.commit()

    def archive_stale(self, max_age_seconds: int = 86400) -> int:
        cutoff = time.time() - max_age_seconds
        stale = self._db.execute(
            "SELECT * FROM sessions WHERE updated_at < ?", (cutoff,)
        ).fetchall()

        now = time.time()
        for row in stale:
            self._db.execute(
                "INSERT INTO session_history (chat_id, session_id, created_at, archived_at) VALUES (?, ?, ?, ?)",
                (row["chat_id"], row["session_id"], row["created_at"], now),
            )
            self._db.execute("DELETE FROM sessions WHERE chat_id = ?", (row["chat_id"],))

        self._db.commit()
        return len(stale)

    def get_history(self, chat_id: int) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM session_history WHERE chat_id = ? ORDER BY archived_at DESC",
            (chat_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def log_usage(self, chat_id: int, cost_usd: float, input_tokens: int, output_tokens: int):
        self._db.execute(
            "INSERT INTO usage_log (chat_id, timestamp, cost_usd, input_tokens, output_tokens) VALUES (?, ?, ?, ?, ?)",
            (chat_id, time.time(), cost_usd, input_tokens, output_tokens),
        )
        self._db.commit()

    def get_usage(self, chat_id: int | None = None) -> dict:
        """Get usage stats. If chat_id is None, returns totals across all chats."""
        from datetime import date, datetime

        today_start = datetime.combine(date.today(), datetime.min.time()).timestamp()

        where = "WHERE chat_id = ?" if chat_id is not None else ""
        params_today = (today_start, chat_id) if chat_id else (today_start,)
        params_all = (chat_id,) if chat_id else ()

        today = self._db.execute(
            f"""SELECT COALESCE(SUM(cost_usd), 0) as cost,
                       COALESCE(SUM(input_tokens), 0) as input_tok,
                       COALESCE(SUM(output_tokens), 0) as output_tok,
                       COUNT(*) as messages
                FROM usage_log {where}{"AND" if where else "WHERE"} timestamp >= ?""",
            params_today if not chat_id else (chat_id, today_start),
        ).fetchone()

        total = self._db.execute(
            f"""SELECT COALESCE(SUM(cost_usd), 0) as cost,
                       COALESCE(SUM(input_tokens), 0) as input_tok,
                       COALESCE(SUM(output_tokens), 0) as output_tok,
                       COUNT(*) as messages
                FROM usage_log {where}""",
            params_all,
        ).fetchone()

        return {
            "today": {
                "cost_usd": today["cost"],
                "input_tokens": today["input_tok"],
                "output_tokens": today["output_tok"],
                "messages": today["messages"],
            },
            "total": {
                "cost_usd": total["cost"],
                "input_tokens": total["input_tok"],
                "output_tokens": total["output_tok"],
                "messages": total["messages"],
            },
        }

    def log_chat(self, chat_id: int, role: str, text: str):
        """Record a user or assistant message to the chat log."""
        self._db.execute(
            "INSERT INTO chat_log (chat_id, timestamp, role, text) VALUES (?, ?, ?, ?)",
            (chat_id, time.time(), role, text),
        )
        self._db.commit()

    def get_chat_history(self, chat_id: int, limit: int = 50) -> list[dict]:
        rows = self._db.execute(
            "SELECT * FROM chat_log WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

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

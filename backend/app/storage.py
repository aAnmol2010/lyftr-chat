import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        self.path = path

    def connect(self):
        return closing(sqlite3.connect(self.path, timeout=5))

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS sessions(session_id TEXT PRIMARY KEY, system_prompt TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS messages(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, metadata TEXT, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_order ON messages(session_id,id);
            """)

    def check(self):
        with self.connect() as db:
            db.execute(
                "SELECT m.id FROM messages m JOIN sessions s USING(session_id) LIMIT 1"
            ).fetchone()

    def load(self, sid, recent_turns=None):
        with self.connect() as db:
            db.execute("BEGIN")
            session = db.execute(
                "SELECT system_prompt FROM sessions WHERE session_id=?", (sid,)
            ).fetchone()
            if session is None:
                return None
            query = "SELECT role,content,metadata FROM messages WHERE session_id=?"
            if recent_turns is None:
                rows = db.execute(query + " ORDER BY id", (sid,))
            else:
                rows = reversed(
                    db.execute(
                        query + " ORDER BY id DESC LIMIT ?", (sid, recent_turns * 2)
                    ).fetchall()
                )
            return session[0], [
                {
                    "role": role,
                    "content": content,
                    **({"metadata": json.loads(meta)} if meta else {}),
                }
                for role, content, meta in rows
            ]

    def commit_turn(self, sid, prompt, message, reply, metadata):
        timestamp = datetime.now(timezone.utc).isoformat()
        with self.connect() as db, db:
            db.execute(
                """INSERT INTO sessions VALUES (?,?) ON CONFLICT(session_id)
                          DO UPDATE SET system_prompt=excluded.system_prompt""",
                (sid, prompt),
            )
            db.executemany(
                "INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES (?,?,?,?,?)",
                [
                    (sid, "user", message, None, timestamp),
                    (sid, "assistant", reply, json.dumps(metadata), timestamp),
                ],
            )

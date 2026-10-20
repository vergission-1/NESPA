"""A deliberately small, auditable SQLite state store.

The database is durable. The demonstration worker is not: interrupted work is
explicitly marked as such after a process restart rather than being faked.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.path, timeout=5)
        con.row_factory = sqlite3.Row
        return con

    def init(self) -> None:
        with self.connect() as con:
            con.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total_steps INTEGER NOT NULL,
                    completed_steps INTEGER NOT NULL DEFAULT 0,
                    interval_ms INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    kind TEXT NOT NULL,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id, id);
                CREATE TABLE IF NOT EXISTS notes (
                    id TEXT PRIMARY KEY,
                    task_id TEXT,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            # Never present stale work as still running after a process restart.
            con.execute("UPDATE tasks SET status='interrupted',updated_at=? WHERE status IN ('queued','running')", (utc_now(),))

    @staticmethod
    def as_dict(row: sqlite3.Row | None) -> dict | None:
        return dict(row) if row else None

    def create_task(self, title: str, total_steps: int, interval_ms: int) -> dict:
        tid, now = uuid4().hex[:12], utc_now()
        with self.connect() as con:
            con.execute(
                "INSERT INTO tasks VALUES (?, ?, 'queued', ?, 0, ?, ?, ?)",
                (tid, title, total_steps, interval_ms, now, now),
            )
            con.execute(
                "INSERT INTO events (task_id,kind,message,created_at) VALUES (?,?,?,?)",
                (tid, "created", "任务已创建，等待 Worker。", now),
            )
        return self.get_task(tid)

    def get_task(self, tid: str) -> dict | None:
        with self.connect() as con:
            return self.as_dict(con.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())

    def list_tasks(self) -> list[dict]:
        with self.connect() as con:
            return [dict(row) for row in con.execute("SELECT * FROM tasks ORDER BY created_at DESC, rowid DESC LIMIT 50")]

    def change_status(self, tid: str, status: str, kind: str, message: str) -> None:
        now = utc_now()
        with self.connect() as con:
            con.execute("UPDATE tasks SET status=?,updated_at=? WHERE id=?", (status, now, tid))
            con.execute(
                "INSERT INTO events (task_id,kind,message,created_at) VALUES (?,?,?,?)",
                (tid, kind, message, now),
            )

    def advance(self, tid: str, step: int) -> None:
        now = utc_now()
        with self.connect() as con:
            con.execute("UPDATE tasks SET completed_steps=?,updated_at=? WHERE id=?", (step, now, tid))
            con.execute(
                "INSERT INTO events (task_id,kind,message,created_at) VALUES (?,?,?,?)",
                (tid, "progress", f"模拟工作步骤 {step} 已完成（示例数据，不代表实际论文分析）。", now),
            )

    def events(self, tid: str, limit: int = 30) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                "SELECT * FROM events WHERE task_id=? ORDER BY id DESC LIMIT ?",
                (tid, limit),
            ).fetchall()
            return [dict(r) for r in reversed(rows)]

    def add_note(self, content: str, tid: str | None = None) -> dict:
        note = {"id": uuid4().hex[:12], "task_id": tid, "content": content, "created_at": utc_now()}
        with self.connect() as con:
            con.execute(
                "INSERT INTO notes (id,task_id,content,created_at) VALUES (?,?,?,?)",
                (note["id"], tid, content, note["created_at"]),
            )
        return note

    def list_notes(self, limit: int = 50) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute("SELECT * FROM notes ORDER BY rowid DESC LIMIT ?", (limit,))]

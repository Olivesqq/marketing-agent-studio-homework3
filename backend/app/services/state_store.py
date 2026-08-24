from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.models import RunMode, RunSnapshot, RunStatus, WorkflowEvent


class StateStore:
    """Small durable run/event store used by SSE and human review."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL DEFAULT 'legacy-local',
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    scenario TEXT,
                    current_stage TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL DEFAULT '{}',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    status TEXT NOT NULL,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id)
                );
                CREATE INDEX IF NOT EXISTS idx_events_run_id_id ON events(run_id, id);
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    comment TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(runs)").fetchall()}
            if "session_id" not in columns:
                connection.execute("ALTER TABLE runs ADD COLUMN session_id TEXT NOT NULL DEFAULT 'legacy-local'")

    def create_run(self, run_id: str, mode: RunMode, goal: str, scenario: str | None, session_id: str = "local-session") -> None:
        now = datetime.utcnow().isoformat()
        with self._lock, self._connect() as connection:
            connection.execute(
                """INSERT INTO runs
                (run_id, session_id, status, mode, goal, scenario, current_stage, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (run_id, session_id, RunStatus.queued.value, mode.value, goal, scenario, "queued", now, now),
            )

    def update_run(
        self,
        run_id: str,
        *,
        status: RunStatus | None = None,
        stage: str | None = None,
        scenario: str | None = None,
        artifacts: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        current = self.get_run(run_id)
        if current is None:
            raise KeyError(run_id)
        next_artifacts = current.artifacts if artifacts is None else artifacts
        with self._lock, self._connect() as connection:
            connection.execute(
                """UPDATE runs SET status=?, current_stage=?, scenario=?, artifacts_json=?,
                error=?, updated_at=? WHERE run_id=?""",
                (
                    (status or current.status).value,
                    stage or current.current_stage,
                    scenario if scenario is not None else current.scenario,
                    json.dumps(next_artifacts, ensure_ascii=False, default=str),
                    error,
                    datetime.utcnow().isoformat(),
                    run_id,
                ),
            )

    def append_event(self, event: WorkflowEvent) -> int:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO events
                (run_id, event, stage, status, title, detail, data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.run_id,
                    event.event,
                    event.stage,
                    event.status,
                    event.title,
                    event.detail,
                    json.dumps(event.data, ensure_ascii=False, default=str),
                    event.created_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def get_events(self, run_id: str, after_id: int = 0) -> list[WorkflowEvent]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE run_id=? AND id>? ORDER BY id", (run_id, after_id)
            ).fetchall()
        return [
            WorkflowEvent(
                id=row["id"],
                run_id=row["run_id"],
                event=row["event"],
                stage=row["stage"],
                status=row["status"],
                title=row["title"],
                detail=row["detail"],
                data=json.loads(row["data_json"]),
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> RunSnapshot | None:
        with self._lock, self._connect() as connection:
            row = connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        return RunSnapshot(
            run_id=row["run_id"],
            status=RunStatus(row["status"]),
            mode=RunMode(row["mode"]),
            goal=row["goal"],
            scenario=row["scenario"],
            current_stage=row["current_stage"],
            artifacts=json.loads(row["artifacts_json"]),
            error=row["error"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def owns_run(self, run_id: str, session_id: str) -> bool:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM runs WHERE run_id=? AND session_id=?", (run_id, session_id)
            ).fetchone()
        return row is not None

    def active_run_count(self, session_id: str) -> int:
        terminal = (RunStatus.completed.value, RunStatus.blocked.value, RunStatus.failed.value, RunStatus.rejected.value)
        placeholders = ",".join("?" for _ in terminal)
        with self._lock, self._connect() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS count FROM runs WHERE session_id=? AND status NOT IN ({placeholders})",
                (session_id, *terminal),
            ).fetchone()
        return int(row["count"])

    def add_review(self, run_id: str, action: str, reviewer: str, comment: str) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                "INSERT INTO reviews (run_id, action, reviewer, comment, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, action, reviewer, comment, datetime.utcnow().isoformat()),
            )

    def clear(self) -> None:
        """Test helper; application code never calls this."""
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM reviews")
            connection.execute("DELETE FROM runs")

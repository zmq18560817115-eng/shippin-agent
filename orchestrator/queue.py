from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
CONFIG_PATH = ROOT / "config" / "orchestrator.yaml"

AGENTS = ("collector", "analysis", "script", "storyboard", "asset", "media", "review")
STATUSES = (
    "queued",
    "running",
    "awaiting_human",
    "succeeded",
    "failed",
    "blocked",
    "needs_review",
    "cancelled",
)


@dataclass(frozen=True)
class Task:
    id: int
    project_id: str
    stage: str
    agent: str
    task_type: str
    status: str
    priority: int
    attempt: int
    max_retries: int
    payload_json: dict[str, Any]
    result_json: dict[str, Any] | None
    error_json: dict[str, Any] | None
    lease_owner: str | None
    lease_expires_at: str | None
    heartbeat_at: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    finished_at: str | None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _iso_after(seconds: int | float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def resolve_db_path(db_path: str | os.PathLike[str] | None = None) -> Path:
    if db_path is not None:
        return Path(db_path)
    env_path = os.environ.get("VAF_DB_PATH")
    if env_path:
        return Path(env_path)
    configured = _load_config().get("database", {}).get("path", "db/agentflow.db")
    path = Path(configured)
    return path if path.is_absolute() else ROOT / path


def resolve_lease_seconds(lease_seconds: int | None = None) -> int:
    if lease_seconds is not None:
        return lease_seconds
    env_value = os.environ.get("VAF_LEASE_SECONDS")
    if env_value:
        return int(env_value)
    return int(_load_config().get("runtime", {}).get("lease_seconds", 60))


def get_conn(db_path: str | os.PathLike[str] | None = None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(db_path: str | os.PathLike[str] | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def ensure_project(
    project_id: str,
    *,
    product_id: str | None = None,
    source_link_id: int | None = None,
    budget_cny: float = 35.0,
    payload: dict[str, Any] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> None:
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, product_id, source_link_id, budget_cny, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                product_id = COALESCE(excluded.product_id, projects.product_id),
                source_link_id = COALESCE(excluded.source_link_id, projects.source_link_id),
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                product_id,
                source_link_id,
                budget_cny,
                _dumps(payload or {}),
                now,
                now,
            ),
        )


def delete_project(project_id: str, *, db_path: str | os.PathLike[str] | None = None) -> None:
    """Delete one finished or stopped project and its database records."""

    with get_conn(db_path) as conn:
        running = conn.execute(
            "SELECT COUNT(*) AS count FROM tasks WHERE project_id = ? AND status IN ('queued', 'running')",
            (project_id,),
        ).fetchone()
        if int(running["count"]):
            raise ValueError("project has queued or running tasks")
        deleted = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,)).rowcount
    if not deleted:
        raise KeyError(project_id)


def enqueue_task(
    *,
    project_id: str,
    stage: str,
    agent: str,
    task_type: str = "default",
    payload: dict[str, Any] | None = None,
    priority: int = 100,
    max_retries: int = 2,
    db_path: str | os.PathLike[str] | None = None,
) -> int:
    if agent not in AGENTS:
        raise ValueError(f"invalid agent: {agent}")
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")
    now = utc_now()
    ensure_project(project_id, db_path=db_path)
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO tasks (
                project_id, stage, agent, task_type, priority, max_retries,
                payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                stage,
                agent,
                task_type,
                priority,
                max_retries,
                _dumps(payload or {}),
                now,
                now,
            ),
        )
        task_id = int(cursor.lastrowid)
        record_event(
            project_id=project_id,
            task_id=task_id,
            event_type="task.enqueued",
            message=f"{agent}:{task_type}:{stage}",
            db_path=db_path,
        )
        return task_id


def claim_task(
    worker_id: str,
    *,
    agents: Sequence[str] | None = None,
    project_id: str | None = None,
    lease_seconds: int | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> Task | None:
    selected_agents = tuple(agents or AGENTS)
    invalid_agents = [agent for agent in selected_agents if agent not in AGENTS]
    if invalid_agents:
        raise ValueError(f"invalid agents: {', '.join(invalid_agents)}")

    recover_expired_leases(db_path=db_path)
    now = utc_now()
    lease_expires_at = _iso_after(resolve_lease_seconds(lease_seconds))
    placeholders = ",".join("?" for _ in selected_agents)
    project_clause = "AND candidate.project_id = ?" if project_id else ""
    sql = f"""
        UPDATE tasks
        SET
            status = 'running',
            attempt = attempt + 1,
            lease_owner = ?,
            lease_expires_at = ?,
            heartbeat_at = ?,
            started_at = COALESCE(started_at, ?),
            updated_at = ?
        WHERE id = (
            SELECT candidate.id
            FROM tasks AS candidate
            WHERE candidate.status = 'queued'
              AND candidate.agent IN ({placeholders})
              {project_clause}
              AND (
                candidate.agent <> 'media'
                OR NOT EXISTS (
                    SELECT 1 FROM tasks AS running_media
                    WHERE running_media.agent = 'media'
                      AND running_media.status = 'running'
                )
              )
            ORDER BY candidate.priority ASC, candidate.created_at ASC, candidate.id ASC
            LIMIT 1
        )
        RETURNING *
    """
    params: list[Any] = [
        worker_id,
        lease_expires_at,
        now,
        now,
        now,
        *selected_agents,
    ]
    if project_id:
        params.append(project_id)
    with get_conn(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
        if row is None:
            return None
        task = _row_to_task(row)
        record_event(
            project_id=task.project_id,
            task_id=task.id,
            event_type="task.claimed",
            message=worker_id,
            meta={"attempt": task.attempt, "lease_expires_at": task.lease_expires_at},
            db_path=db_path,
        )
        return task


def claim_task_by_id(
    task_id: int,
    worker_id: str,
    *,
    lease_seconds: int | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> Task | None:
    recover_expired_leases(db_path=db_path)
    now = utc_now()
    lease_expires_at = _iso_after(resolve_lease_seconds(lease_seconds))
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            UPDATE tasks
            SET status = 'running',
                attempt = attempt + 1,
                lease_owner = ?,
                lease_expires_at = ?,
                heartbeat_at = ?,
                started_at = COALESCE(started_at, ?),
                updated_at = ?
            WHERE id = ? AND status = 'queued'
            RETURNING *
            """,
            (worker_id, lease_expires_at, now, now, now, task_id),
        ).fetchone()
        if row is None:
            return None
        task = _row_to_task(row)
        record_event(
            project_id=task.project_id,
            task_id=task.id,
            event_type="task.claimed",
            message=worker_id,
            meta={"attempt": task.attempt, "lease_expires_at": task.lease_expires_at},
            db_path=db_path,
        )
        return task


def heartbeat_task(
    task_id: int,
    worker_id: str,
    *,
    lease_seconds: int | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    now = utc_now()
    lease_expires_at = _iso_after(resolve_lease_seconds(lease_seconds))
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            UPDATE tasks
            SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (now, lease_expires_at, now, task_id, worker_id),
        )
        return cursor.rowcount == 1


def complete_task(
    task_id: int,
    worker_id: str,
    result: dict[str, Any] | None = None,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> None:
    now = utc_now()
    with get_conn(db_path) as conn:
        row = conn.execute(
            """
            UPDATE tasks
            SET status = 'succeeded',
                result_json = ?,
                error_json = NULL,
                lease_owner = NULL,
                lease_expires_at = NULL,
                heartbeat_at = NULL,
                updated_at = ?,
                finished_at = ?
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            RETURNING project_id
            """,
            (_dumps(result or {}), now, now, task_id, worker_id),
        ).fetchone()
        if row is None:
            raise RuntimeError(f"task {task_id} is not running for worker {worker_id}")
        record_event(
            project_id=row["project_id"],
            task_id=task_id,
            event_type="task.succeeded",
            db_path=db_path,
        )


def fail_task(
    task_id: int,
    worker_id: str,
    error: dict[str, Any],
    *,
    retryable: bool,
    db_path: str | os.PathLike[str] | None = None,
) -> str:
    task = get_task(task_id, db_path=db_path)
    if task.lease_owner != worker_id or task.status != "running":
        raise RuntimeError(f"task {task_id} is not running for worker {worker_id}")
    next_status = "queued" if retryable and task.attempt < task.max_retries else "failed"
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?,
                error_json = ?,
                lease_owner = NULL,
                lease_expires_at = NULL,
                heartbeat_at = NULL,
                updated_at = ?,
                finished_at = CASE WHEN ? = 'failed' THEN ? ELSE finished_at END
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (next_status, _dumps(error), now, next_status, now, task_id, worker_id),
        )
    record_event(
        project_id=task.project_id,
        task_id=task.id,
        event_type="task.retry" if next_status == "queued" else "task.failed",
        meta={"attempt": task.attempt, "max_retries": task.max_retries, "error": error},
        db_path=db_path,
    )
    return next_status


def mark_task_status(
    task_id: int,
    status: str,
    *,
    worker_id: str | None = None,
    result: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> None:
    if status not in STATUSES:
        raise ValueError(f"invalid status: {status}")
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = ?,
                result_json = ?,
                error_json = ?,
                lease_owner = NULL,
                lease_expires_at = NULL,
                heartbeat_at = NULL,
                updated_at = ?,
                finished_at = CASE
                    WHEN ? IN ('succeeded','failed','blocked','cancelled') THEN ?
                    ELSE finished_at
                END
            WHERE id = ?
              AND (? IS NULL OR lease_owner = ?)
            """,
            (
                status,
                _dumps(result) if result is not None else None,
                _dumps(error) if error is not None else None,
                now,
                status,
                now,
                task_id,
                worker_id,
                worker_id,
            ),
        )


def recover_expired_leases(
    *,
    db_path: str | os.PathLike[str] | None = None,
    now: str | None = None,
) -> int:
    recovery_time = now or utc_now()
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, project_id, attempt, max_retries
            FROM tasks
            WHERE status = 'running'
              AND lease_expires_at IS NOT NULL
              AND lease_expires_at <= ?
            """,
            (recovery_time,),
        ).fetchall()
        recovered = 0
        for row in rows:
            next_status = "queued" if int(row["attempt"]) < int(row["max_retries"]) else "failed"
            error = {
                "category": "lease_expired",
                "message": "worker lease expired before task completion",
                "attempt": int(row["attempt"]),
                "max_retries": int(row["max_retries"]),
            }
            conn.execute(
                """
                UPDATE tasks
                SET status = ?,
                    error_json = ?,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    heartbeat_at = NULL,
                    updated_at = ?,
                    finished_at = CASE WHEN ? = 'failed' THEN ? ELSE finished_at END
                WHERE id = ?
                """,
                (next_status, _dumps(error), recovery_time, next_status, recovery_time, row["id"]),
            )
            recovered += 1
            record_event(
                project_id=row["project_id"],
                task_id=int(row["id"]),
                event_type="task.lease_recovered",
                meta={"next_status": next_status, "attempt": int(row["attempt"])},
                db_path=db_path,
            )
        return recovered


def recover_running_tasks_on_startup(
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> int:
    """Requeue tasks orphaned when the single local orchestrator stopped."""
    recovery_time = utc_now()
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, project_id, attempt, max_retries FROM tasks WHERE status = 'running'"
        ).fetchall()
        for row in rows:
            next_status = "queued" if int(row["attempt"]) < int(row["max_retries"]) else "failed"
            error = {
                "category": "service_restarted",
                "message": "task was recovered after the local orchestrator restarted",
                "attempt": int(row["attempt"]),
                "max_retries": int(row["max_retries"]),
            }
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, error_json = ?, lease_owner = NULL,
                    lease_expires_at = NULL, heartbeat_at = NULL, updated_at = ?,
                    finished_at = CASE WHEN ? = 'failed' THEN ? ELSE NULL END
                WHERE id = ?
                """,
                (next_status, _dumps(error), recovery_time, next_status, recovery_time, row["id"]),
            )
            record_event(
                project_id=row["project_id"],
                task_id=int(row["id"]),
                event_type="task.startup_recovered",
                meta={"next_status": next_status, "attempt": int(row["attempt"])},
                db_path=db_path,
            )
        return len(rows)


def requeue_task(
    task_id: int,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> Task:
    task = get_task(task_id, db_path=db_path)
    if task.status not in {"failed", "blocked", "cancelled"}:
        raise ValueError(f"task {task_id} is not retryable from status {task.status}")
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE tasks
            SET status = 'queued', attempt = 0, error_json = NULL,
                lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
                updated_at = ?, started_at = NULL, finished_at = NULL
            WHERE id = ?
            """,
            (now, task_id),
        )
    record_event(
        project_id=task.project_id,
        task_id=task_id,
        event_type="task.manual_retry",
        message=task.stage,
        db_path=db_path,
    )
    return get_task(task_id, db_path=db_path)


def get_task(task_id: int, *, db_path: str | os.PathLike[str] | None = None) -> Task:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        raise KeyError(f"task not found: {task_id}")
    return _row_to_task(row)


def list_tasks(
    *,
    status: str | None = None,
    project_id: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> list[Task]:
    clauses: list[str] = []
    params: list[Any] = []
    if status is not None:
        clauses.append("status = ?")
        params.append(status)
    if project_id is not None:
        clauses.append("project_id = ?")
        params.append(project_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM tasks {where} ORDER BY priority ASC, created_at ASC, id ASC",
            params,
        ).fetchall()
    return [_row_to_task(row) for row in rows]


def record_event(
    *,
    event_type: str,
    project_id: str | None = None,
    task_id: int | None = None,
    message: str | None = None,
    meta: dict[str, Any] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO events(project_id, task_id, event_type, message, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_id, task_id, event_type, message, _dumps(meta or {}), utc_now()),
        )


def _row_to_task(row: sqlite3.Row) -> Task:
    return Task(
        id=int(row["id"]),
        project_id=str(row["project_id"]),
        stage=str(row["stage"]),
        agent=str(row["agent"]),
        task_type=str(row["task_type"]),
        status=str(row["status"]),
        priority=int(row["priority"]),
        attempt=int(row["attempt"]),
        max_retries=int(row["max_retries"]),
        payload_json=_loads(row["payload_json"]),
        result_json=_loads_optional(row["result_json"]),
        error_json=_loads_optional(row["error_json"]),
        lease_owner=row["lease_owner"],
        lease_expires_at=row["lease_expires_at"],
        heartbeat_at=row["heartbeat_at"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


def _dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _loads(value: str | bytes | None) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {"value": loaded}


def _loads_optional(value: str | bytes | None) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    return _loads(value)

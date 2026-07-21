from __future__ import annotations

import json
import os
import re
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
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(collector_schedules)").fetchall()}
        if "failure_count" not in columns:
            conn.execute("ALTER TABLE collector_schedules ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0")
        if "next_run_at" not in columns:
            conn.execute("ALTER TABLE collector_schedules ADD COLUMN next_run_at TEXT")
        job_columns = {row["name"] for row in conn.execute("PRAGMA table_info(collection_jobs)").fetchall()}
        collection_job_migrations = {
            "max_attempts": "ALTER TABLE collection_jobs ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
            "next_attempt_at": "ALTER TABLE collection_jobs ADD COLUMN next_attempt_at TEXT",
            "lease_owner": "ALTER TABLE collection_jobs ADD COLUMN lease_owner TEXT",
            "lease_expires_at": "ALTER TABLE collection_jobs ADD COLUMN lease_expires_at TEXT",
            "heartbeat_at": "ALTER TABLE collection_jobs ADD COLUMN heartbeat_at TEXT",
        }
        for name, statement in collection_job_migrations.items():
            if name not in job_columns:
                conn.execute(statement)


def create_collection_job(
    *,
    target_type: str,
    provider: str,
    target: str,
    requested_count: int,
    product_id: str,
    mock: bool,
    created_by: str = "operator",
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    if target_type not in {"keyword", "account", "hashtag", "trending"}:
        raise ValueError("unsupported target_type")
    if provider not in {"auto", "tiktok_api", "apify", "yt_dlp"}:
        raise ValueError("unsupported provider")
    if target_type != "trending" and not target.strip():
        raise ValueError("target is required")
    count = max(1, min(int(requested_count), 100))
    now = utc_now()
    init_db(db_path)
    with get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO collection_jobs
            (target_type, provider, target, requested_count, product_id, mock, status, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (target_type, provider, target.strip(), count, product_id, int(mock), created_by, now, now),
        )
        job_id = int(cursor.lastrowid)
    job = get_collection_job(job_id, db_path=db_path)
    if job is None:
        raise RuntimeError("collection job was not persisted")
    return job


def get_collection_job(
    job_id: int,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM collection_jobs WHERE id = ?", (job_id,)).fetchone()
    return _collection_job_dict(row) if row else None


def list_collection_jobs(
    *,
    status: str | None = None,
    limit: int = 50,
    db_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    params: list[Any] = []
    where = ""
    if status:
        where = "WHERE status = ?"
        params.append(status)
    params.append(max(1, min(int(limit), 200)))
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM collection_jobs {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [_collection_job_dict(row) for row in rows]


def cancel_collection_job(
    job_id: int,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    now = utc_now()
    with get_conn(db_path) as conn:
        changed = conn.execute(
            """
            UPDATE collection_jobs
            SET status = 'cancelled', finished_at = ?, updated_at = ?
            WHERE id = ? AND status IN ('queued','paused')
            """,
            (now, now, job_id),
        ).rowcount
    if not changed:
        return None
    return get_collection_job(job_id, db_path=db_path)


def claim_collection_job(
    worker_id: str,
    *,
    lease_seconds: int = 900,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any] | None:
    init_db(db_path)
    recover_expired_collection_jobs(db_path=db_path)
    now = utc_now()
    lease_expires = _iso_after(max(30, int(lease_seconds)))
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id FROM collection_jobs
            WHERE status = 'queued'
              AND attempt < max_attempts
              AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
            ORDER BY created_at, id
            LIMIT 1
            """,
            (now,),
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None
        changed = conn.execute(
            """
            UPDATE collection_jobs
            SET status = 'running', attempt = attempt + 1, lease_owner = ?, lease_expires_at = ?,
                heartbeat_at = ?, started_at = COALESCE(started_at, ?), updated_at = ?, error_message = ''
            WHERE id = ? AND status = 'queued'
            """,
            (worker_id, lease_expires, now, now, now, int(row["id"])),
        ).rowcount
        conn.execute("COMMIT")
    return get_collection_job(int(row["id"]), db_path=db_path) if changed else None


def heartbeat_collection_job(
    job_id: int,
    worker_id: str,
    *,
    lease_seconds: int = 900,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    now = utc_now()
    with get_conn(db_path) as conn:
        changed = conn.execute(
            """
            UPDATE collection_jobs
            SET heartbeat_at = ?, lease_expires_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (now, _iso_after(max(30, int(lease_seconds))), now, job_id, worker_id),
        ).rowcount
    return bool(changed)


def complete_collection_job(
    job_id: int,
    worker_id: str,
    *,
    discovered_count: int,
    relevant_count: int,
    downloaded_count: int,
    analyzed_count: int,
    failed_count: int,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    with get_conn(db_path) as conn:
        lease = conn.execute(
            "SELECT requested_count FROM collection_jobs WHERE id = ? AND status = 'running' AND lease_owner = ?",
            (job_id, worker_id),
        ).fetchone()
        if lease is None:
            raise RuntimeError("collection job lease is no longer owned by this worker")
        requested_count = int(lease["requested_count"] or 0)
        final_status = (
            "succeeded"
            if analyzed_count >= requested_count and failed_count == 0
            else "partial"
            if analyzed_count >= 1
            else "failed"
        )
        changed = conn.execute(
            """
            UPDATE collection_jobs
            SET status = ?, discovered_count = ?, relevant_count = ?, downloaded_count = ?, analyzed_count = ?,
                failed_count = ?, lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
                next_attempt_at = NULL, finished_at = ?, updated_at = ?
            WHERE id = ? AND status = 'running' AND lease_owner = ?
            """,
            (
                final_status, max(0, discovered_count), max(0, relevant_count), max(0, downloaded_count),
                max(0, analyzed_count), max(0, failed_count), now, now, job_id, worker_id,
            ),
        ).rowcount
    if not changed:
        raise RuntimeError("collection job lease is no longer owned by this worker")
    job = get_collection_job(job_id, db_path=db_path)
    if job is None:
        raise RuntimeError("collection job disappeared after completion")
    return job


def fail_collection_job(
    job_id: int,
    worker_id: str,
    error: str,
    *,
    retryable: bool = True,
    retry_after_seconds: int | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    now = utc_now()
    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT attempt, max_attempts FROM collection_jobs WHERE id = ? AND status = 'running' AND lease_owner = ?",
            (job_id, worker_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("collection job lease is no longer owned by this worker")
        can_retry = retryable and int(row["attempt"]) < int(row["max_attempts"])
        delay = retry_after_seconds if retry_after_seconds is not None else min(3600, 60 * (2 ** max(0, int(row["attempt"]) - 1)))
        next_attempt = _iso_after(max(1, delay)) if can_retry else None
        conn.execute(
            """
            UPDATE collection_jobs
            SET status = ?, error_message = ?, next_attempt_at = ?, lease_owner = NULL,
                lease_expires_at = NULL, heartbeat_at = NULL, finished_at = ?, updated_at = ?
            WHERE id = ? AND lease_owner = ?
            """,
            ("queued" if can_retry else "failed", str(error)[:2000], next_attempt, None if can_retry else now, now, job_id, worker_id),
        )
    job = get_collection_job(job_id, db_path=db_path)
    if job is None:
        raise RuntimeError("collection job disappeared after failure")
    return job


def recover_expired_collection_jobs(
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> int:
    init_db(db_path)
    now = utc_now()
    with get_conn(db_path) as conn:
        changed = conn.execute(
            """
            UPDATE collection_jobs
            SET status = CASE WHEN attempt < max_attempts THEN 'queued' ELSE 'failed' END,
                error_message = 'Worker 租约过期，任务已恢复', next_attempt_at = NULL,
                lease_owner = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
                finished_at = CASE WHEN attempt < max_attempts THEN NULL ELSE ? END, updated_at = ?
            WHERE status = 'running' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?
            """,
            (now, now, now),
        ).rowcount
    return int(changed)


def collection_url_exists(
    source_url: str,
    *,
    exclude_job_id: int | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> bool:
    init_db(db_path)
    params: list[Any] = [source_url]
    extra = ""
    if exclude_job_id is not None:
        extra = "AND job_id != ?"
        params.append(exclude_job_id)
    with get_conn(db_path) as conn:
        row = conn.execute(
            f"SELECT 1 FROM collection_items WHERE source_url = ? {extra} AND status NOT IN ('failed','filtered') LIMIT 1",
            params,
        ).fetchone()
    return row is not None


def upsert_collection_item(
    job_id: int,
    *,
    source_url: str,
    item: dict[str, Any],
    relevance_score: float,
    status: str,
    error_message: str = "",
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    allowed = {"discovered", "filtered", "downloading", "downloaded", "transcribing", "analyzing", "ready", "failed"}
    if status not in allowed:
        raise ValueError("unsupported collection item status")
    now = utc_now()
    video_id = str(item.get("video_id") or "")
    if not video_id:
        match = re.search(r"/video/(\d+)", source_url)
        video_id = match.group(1) if match else ""
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO collection_items
            (job_id, source_url, source_video_id, title, author_name, cover_url, relevance_score,
             status, error_message, metadata_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, source_url) DO UPDATE SET
                source_video_id = excluded.source_video_id, title = excluded.title,
                author_name = excluded.author_name, cover_url = excluded.cover_url,
                relevance_score = excluded.relevance_score, status = excluded.status,
                error_message = excluded.error_message, metadata_json = excluded.metadata_json,
                updated_at = excluded.updated_at
            """,
            (
                job_id, source_url, video_id,
                str(item.get("title") or item.get("caption") or "")[:500],
                str(item.get("author_name") or item.get("author") or "")[:200],
                str(item.get("cover_url") or item.get("thumbnail_url") or "")[:2000],
                max(0.0, min(float(relevance_score), 1.0)), status, str(error_message)[:2000],
                _dumps(item), now, now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM collection_items WHERE job_id = ? AND source_url = ?",
            (job_id, source_url),
        ).fetchone()
    return _collection_item_dict(row)


def list_collection_items(
    job_id: int,
    *,
    status: str | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    init_db(db_path)
    params: list[Any] = [job_id]
    extra = ""
    if status:
        extra = "AND status = ?"
        params.append(status)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM collection_items WHERE job_id = ? {extra} ORDER BY relevance_score DESC, id",
            params,
        ).fetchall()
    return [_collection_item_dict(row) for row in rows]


def _collection_item_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    try:
        payload["metadata"] = json.loads(payload.pop("metadata_json") or "{}")
    except json.JSONDecodeError:
        payload["metadata"] = {}
    return payload


def _collection_job_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["mock"] = bool(payload.get("mock"))
    payload["progress"] = {
        "requested": int(payload.get("requested_count") or 0),
        "discovered": int(payload.get("discovered_count") or 0),
        "relevant": int(payload.get("relevant_count") or 0),
        "downloaded": int(payload.get("downloaded_count") or 0),
        "analyzed": int(payload.get("analyzed_count") or 0),
        "failed": int(payload.get("failed_count") or 0),
    }
    return payload


def ensure_project(
    project_id: str,
    *,
    product_id: str | None = None,
    source_link_id: int | None = None,
    budget_cny: float = 35.0,
    budget_mode: str = "enforce",
    payload: dict[str, Any] | None = None,
    db_path: str | os.PathLike[str] | None = None,
) -> None:
    if budget_mode not in {"observe", "enforce"}:
        raise ValueError("budget_mode must be observe or enforce")
    now = utc_now()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, product_id, source_link_id, budget_cny, budget_mode, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                budget_mode,
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


def list_events(
    *,
    event_type: str | None = None,
    limit: int = 100,
    db_path: str | os.PathLike[str] | None = None,
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, min(int(limit), 500)))
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT id, project_id, task_id, event_type, message, meta_json, created_at FROM events {where} ORDER BY created_at DESC, id DESC LIMIT ?",
            params,
        ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "project_id": row["project_id"],
            "task_id": row["task_id"],
            "event_type": str(row["event_type"]),
            "message": row["message"],
            "meta": _loads(row["meta_json"]),
            "created_at": str(row["created_at"]),
        }
        for row in rows
    ]


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

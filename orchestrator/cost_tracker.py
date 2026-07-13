from __future__ import annotations

import json
import os
from typing import Any

from orchestrator import queue


def reconcile(
    *,
    project_id: str,
    agent: str,
    tool: str,
    cost_cny: float,
    db_path: str | os.PathLike[str] | None = None,
    task_id: int | None = None,
    tokens: dict[str, int] | None = None,
    model: str | None = None,
    shot_index: int | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    if cost_cny < 0:
        raise ValueError("cost_cny must be >= 0")
    queue.ensure_project(project_id, db_path=db_path)
    payload = dict(meta or {})
    payload.update(
        {
            "budget_mode": "observe",
            "tokens": tokens or {},
            "model": model,
            "shot_index": shot_index,
        }
    )
    with queue.get_conn(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO cost_entries (
                project_id, task_id, agent, tool, cost_cny, meta_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                task_id,
                agent,
                tool,
                float(cost_cny),
                dumps_meta(payload),
                queue.utc_now(),
            ),
        )
        entry_id = int(cursor.lastrowid)
    queue.record_event(
        project_id=project_id,
        task_id=task_id,
        event_type="cost.reconciled",
        message=f"{tool}:{cost_cny:.4f}",
        meta=payload,
        db_path=db_path,
    )
    return entry_id


def get_project_cost(
    project_id: str,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    with queue.get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(cost_cny), 0.0) AS total_cost_cny,
                COUNT(*) AS entry_count
            FROM cost_entries
            WHERE project_id = ?
            """,
            (project_id,),
        ).fetchone()
    return {
        "project_id": project_id,
        "budget_mode": "observe",
        "total_cost_cny": float(row["total_cost_cny"]),
        "entry_count": int(row["entry_count"]),
    }


def get_task_cost(
    task_id: int,
    *,
    db_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    with queue.get_conn(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(cost_cny), 0.0) AS total_cost_cny,
                COUNT(*) AS entry_count
            FROM cost_entries
            WHERE task_id = ?
            """,
            (task_id,),
        ).fetchone()
    return {
        "task_id": task_id,
        "budget_mode": "observe",
        "total_cost_cny": float(row["total_cost_cny"]),
        "entry_count": int(row["entry_count"]),
    }


def dumps_meta(meta: dict[str, Any]) -> str:
    return json.dumps(meta, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def loads_meta(meta_json: str | bytes | None) -> dict[str, Any]:
    if meta_json in (None, ""):
        return {}
    loaded = json.loads(meta_json)
    return loaded if isinstance(loaded, dict) else {"value": loaded}

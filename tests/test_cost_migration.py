from __future__ import annotations

import sqlite3
from pathlib import Path

from orchestrator import queue


def _create_legacy_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE projects (
                id TEXT PRIMARY KEY,
                product_id TEXT,
                source_link_id INTEGER,
                status TEXT NOT NULL DEFAULT 'queued',
                budget_cny REAL NOT NULL DEFAULT 35.0,
                budget_mode TEXT NOT NULL DEFAULT 'observe',
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                finished_at TEXT
            );
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                agent TEXT NOT NULL,
                task_type TEXT NOT NULL DEFAULT 'default',
                status TEXT NOT NULL DEFAULT 'queued',
                priority INTEGER NOT NULL DEFAULT 100,
                attempt INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 2,
                payload_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                error_json TEXT,
                lease_owner TEXT,
                lease_expires_at TEXT,
                heartbeat_at TEXT,
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                started_at TEXT,
                finished_at TEXT
            );
            CREATE TABLE cost_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                task_id INTEGER,
                agent TEXT,
                tool TEXT,
                cost_cny REAL NOT NULL DEFAULT 0.0,
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            );
            """
        )
        conn.execute(
            "INSERT INTO projects (id, product_id) VALUES ('real-e2e-20260713-1559', '便携恒温杯')"
        )
        conn.execute(
            """
            INSERT INTO cost_entries (id, project_id, task_id, agent, tool, cost_cny, meta_json, created_at)
            VALUES (1, 'real-e2e-20260713-1559', NULL, 'analysis', 'doubao_analyze', 1.23, '{}', '2026-07-13T15:59:00.000Z')
            """
        )
        conn.execute(
            """
            INSERT INTO cost_entries (id, project_id, task_id, agent, tool, cost_cny, meta_json, created_at)
            VALUES (2, 'real-e2e-20260713-1559', NULL, 'media', 'seedance_shot', 4.5, '{}', '2026-07-13T16:02:00.000Z')
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_migration_preserves_legacy_cost_entries_and_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    _create_legacy_db(db_path)

    # First init_db() run must detect the old shape and migrate without losing rows.
    queue.init_db(db_path=db_path)

    with queue.get_conn(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(cost_entries)").fetchall()}
        rows = conn.execute(
            "SELECT entry_id, tool, operation, phase, amount_cny FROM cost_entries ORDER BY entry_id"
        ).fetchall()

    assert columns == {
        "entry_id", "project_id", "task_id", "agent", "tool",
        "operation", "phase", "amount_cny", "meta_json", "created_at",
    }
    assert [dict(row) for row in rows] == [
        {"entry_id": 1, "tool": "doubao_analyze", "operation": "reconcile", "phase": None, "amount_cny": 1.23},
        {"entry_id": 2, "tool": "seedance_shot", "operation": "reconcile", "phase": None, "amount_cny": 4.5},
    ]

    # Second init_db() run (idempotent) must be a no-op: same rows, no crash on re-migration.
    queue.init_db(db_path=db_path)
    with queue.get_conn(db_path) as conn:
        rows_again = conn.execute("SELECT entry_id, tool, amount_cny FROM cost_entries ORDER BY entry_id").fetchall()
    assert [dict(row) for row in rows_again] == [
        {"entry_id": 1, "tool": "doubao_analyze", "amount_cny": 1.23},
        {"entry_id": 2, "tool": "seedance_shot", "amount_cny": 4.5},
    ]


def test_fresh_db_gets_new_cost_entries_shape_directly(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    with queue.get_conn(db_path) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(cost_entries)").fetchall()}
    assert "entry_id" in columns
    assert "amount_cny" in columns
    assert "operation" in columns
    assert "phase" in columns

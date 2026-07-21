from pathlib import Path

import pytest

from orchestrator import queue


def test_v2_task_defaults_and_project_budget(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)

    task_id = queue.enqueue_task(
        project_id="ref-schema",
        stage="analysis",
        agent="analysis",
        db_path=db_path,
    )
    task = queue.get_task(task_id, db_path=db_path)

    assert task.agent == "analysis"
    assert task.task_type == "default"
    assert task.max_retries == 2

    with queue.get_conn(db_path) as conn:
        project = conn.execute(
            "SELECT budget_cny, budget_mode FROM projects WHERE id = ?",
            ("ref-schema",),
        ).fetchone()

    assert project["budget_cny"] == 35.0
    assert project["budget_mode"] == "enforce"


def test_agent_enum_rejects_unknown_agent(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)

    with pytest.raises(ValueError, match="invalid agent"):
        queue.enqueue_task(
            project_id="ref-schema",
            stage="unknown",
            agent="dummy",
            db_path=db_path,
        )


def test_manual_requeue_resets_failed_task(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(project_id="retry-demo", stage="analysis", agent="analysis", db_path=db_path)
    claimed = queue.claim_task_by_id(task_id, "worker", db_path=db_path)
    assert claimed is not None
    queue.fail_task(task_id, "worker", {"category": "provider", "message": "failed"}, retryable=False, db_path=db_path)

    retried = queue.requeue_task(task_id, db_path=db_path)

    assert retried.status == "queued"
    assert retried.attempt == 0
    assert retried.error_json is None


def test_startup_recovery_requeues_orphaned_running_task(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(project_id="restart-demo", stage="analysis", agent="analysis", db_path=db_path)
    assert queue.claim_task_by_id(task_id, "old-process", lease_seconds=1200, db_path=db_path)

    recovered = queue.recover_running_tasks_on_startup(db_path=db_path)

    assert recovered == 1
    task = queue.get_task(task_id, db_path=db_path)
    assert task.status == "queued"
    assert task.error_json["category"] == "service_restarted"


def test_expired_recovery_handles_legacy_running_task_without_lease(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(project_id="legacy-demo", stage="analysis", agent="analysis", db_path=db_path)
    with queue.get_conn(db_path) as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running', lease_owner = NULL, lease_expires_at = NULL, updated_at = ? WHERE id = ?",
            ("2026-07-15T00:00:00.000Z", task_id),
        )

    recovered = queue.recover_expired_leases(now="2026-07-21T00:00:00.000Z", db_path=db_path)

    assert recovered == 1
    task = queue.get_task(task_id, db_path=db_path)
    assert task.status == "queued"
    assert task.error_json["category"] == "legacy_running_recovered"

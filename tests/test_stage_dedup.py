from __future__ import annotations

from pathlib import Path

from orchestrator import engine, queue


def test_stage_dedup_allows_new_upstream_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path)
    queue.enqueue_task(
        project_id="revision-demo",
        stage="script_review",
        agent="review",
        payload={"upstream_task_id": 10},
        db_path=db_path,
    )
    assert engine._stage_task_exists(
        "revision-demo", "script_review", {"upstream_task_id": 10}, db_path=db_path
    )
    assert not engine._stage_task_exists(
        "revision-demo", "script_review", {"upstream_task_id": 11}, db_path=db_path
    )


def test_production_retry_uses_latest_attempt_for_revision(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path)
    queue.ensure_project("production-retry", db_path=db_path)
    first = queue.enqueue_task(
        project_id="production-retry",
        stage="production",
        agent="media",
        payload={"shot_index": 1, "revision": 3},
        db_path=db_path,
    )
    claimed = queue.claim_task("worker", agents=["media"], db_path=db_path)
    assert claimed and claimed.id == first
    queue.fail_task(
        first,
        "worker",
        {"message": "bad request"},
        retryable=False,
        db_path=db_path,
    )
    retry = queue.enqueue_task(
        project_id="production-retry",
        stage="production",
        agent="media",
        payload={"shot_index": 1, "revision": 3},
        db_path=db_path,
    )
    claimed = queue.claim_task("worker", agents=["media"], db_path=db_path)
    assert claimed and claimed.id == retry
    queue.complete_task(retry, "worker", {}, db_path=db_path)

    assert engine._all_production_succeeded(
        "production-retry", revision=3, db_path=db_path
    )
    assert engine._terminal_status(
        "production-retry", tmp_path / "runs" / "production-retry", db_path=db_path
    ) is None

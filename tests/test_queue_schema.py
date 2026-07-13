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
    assert project["budget_mode"] == "observe"


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

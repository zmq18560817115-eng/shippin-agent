from pathlib import Path

from libshared import checkpoint
from orchestrator import cost_tracker, queue


def test_stage_order_matches_v2_manual() -> None:
    assert checkpoint.STAGE_ORDER == [
        "analysis",
        "script",
        "script_review",
        "script_gate",
        "storyboard",
        "asset",
        "hero_gate",
        "production",
        "compose",
        "final_qa",
        "archive",
    ]


def test_task_cost_rollup(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(
        project_id="ref-task-cost",
        stage="production",
        agent="media",
        task_type="shot_gen",
        db_path=db_path,
    )

    cost_tracker.reconcile(
        project_id="ref-task-cost",
        task_id=task_id,
        agent="media",
        tool="seedance_shot",
        cost_cny=1.25,
        db_path=db_path,
    )
    cost_tracker.reconcile(
        project_id="ref-task-cost",
        task_id=task_id,
        agent="media",
        tool="seedance_shot",
        cost_cny=2.75,
        db_path=db_path,
    )

    assert cost_tracker.get_task_cost(task_id, db_path=db_path) == {
        "task_id": task_id,
        "budget_mode": "observe",
        "total_cost_cny": 4.0,
        "entry_count": 2,
    }

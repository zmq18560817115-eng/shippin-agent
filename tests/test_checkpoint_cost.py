from pathlib import Path

import pytest

from libshared import checkpoint
from orchestrator import cost_tracker, queue


def test_stage_order_matches_v2_manual() -> None:
    assert checkpoint.STAGE_ORDER == [
        "analysis",
        "research",
        "strategy",
        "script",
        "script_breakdown",
        "script_review",
        "script_gate",
        "storyboard",
        "asset",
        "hero_gate",
        "production",
        "take_gate",
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
        "budget_mode": "enforce",
        "total_cost_cny": 4.0,
        "entry_count": 2,
    }


def test_enforce_budget_blocks_projected_overspend(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    queue.ensure_project("budgeted", budget_cny=2.0, budget_mode="enforce", db_path=db_path)
    cost_tracker.reconcile(
        project_id="budgeted", agent="media", tool="seedance_shot", cost_cny=1.5, db_path=db_path
    )

    with pytest.raises(cost_tracker.BudgetExceededError, match="预算不足"):
        cost_tracker.require_budget("budgeted", 1.0, db_path=db_path)


def test_observe_budget_allows_projected_overspend(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    queue.ensure_project("observed", budget_cny=1.0, budget_mode="observe", db_path=db_path)

    status = cost_tracker.require_budget("observed", 3.0, db_path=db_path)

    assert status["allowed"] is True
    assert status["projected_cny"] == 3.0

from pathlib import Path

import pytest

from orchestrator import engine, queue


def test_approve_unknown_gate_rejected(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "ref-engine"
    queue.init_db(db_path=db_path)
    engine.start_pipeline(
        "ref-engine",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )

    with pytest.raises(ValueError, match="unknown gate"):
        engine.approve_gate(
            "ref-engine",
            "not_a_gate",
            approver="qa",
            db_path=db_path,
            run_root=run_root,
        )


def test_start_pipeline_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "ref-engine"
    queue.init_db(db_path=db_path)

    first = engine.start_pipeline(
        "ref-engine",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )
    second = engine.start_pipeline(
        "ref-engine",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )

    assert first == second
    assert len(queue.list_tasks(project_id="ref-engine", db_path=db_path)) == 1

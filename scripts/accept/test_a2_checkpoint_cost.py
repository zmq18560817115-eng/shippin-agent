from __future__ import annotations

from pathlib import Path

import pytest

from libshared import checkpoint
from orchestrator import cost_tracker, queue


def test_a2_checkpoint_sequence_tmp_tolerance_and_next_stage(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "ref-a2"
    checkpoint.write_checkpoint(
        "ref-a2",
        "analysis",
        status="succeeded",
        artifacts={"analysis_report": "artifacts/analysis_report.json"},
        run_root=run_root,
    )
    checkpoint.write_checkpoint(
        "ref-a2",
        "script",
        status="succeeded",
        artifacts={"script_copy": "artifacts/script_copy.json"},
        run_root=run_root,
    )
    (run_root / "pipeline" / "999999.tmp").write_text("{not-json", encoding="utf-8")

    latest = checkpoint.read_latest("ref-a2", run_root=run_root)

    assert latest is not None
    assert latest["seq"] == 2
    assert latest["stage"] == "script"
    assert latest["status"] == "succeeded"
    assert checkpoint.get_completed_stages("ref-a2", run_root=run_root) == [
        "analysis",
        "script",
    ]
    assert checkpoint.get_next_stage("ref-a2", run_root=run_root) == "script_review"
    assert checkpoint.resolve_artifact("ref-a2", "script_copy", run_root=run_root) == (
        run_root / "artifacts" / "script_copy.json"
    )


def test_a2_approve_gate_requires_awaiting_human(tmp_path: Path) -> None:
    run_root = tmp_path / "runs" / "ref-gate"
    checkpoint.write_checkpoint(
        "ref-gate",
        "script_gate",
        status="running",
        run_root=run_root,
    )

    with pytest.raises(checkpoint.GateApprovalError):
        checkpoint.approve_gate("ref-gate", "script_gate", approver="qa", run_root=run_root)

    checkpoint.write_checkpoint(
        "ref-gate",
        "script_gate",
        status="awaiting_human",
        run_root=run_root,
    )
    approved = checkpoint.approve_gate(
        "ref-gate",
        "script_gate",
        approver="qa",
        notes="copy ok",
        run_root=run_root,
    )

    assert approved["status"] == "succeeded"
    assert approved["approved_by"] == "qa"
    assert approved["approval_notes"] == "copy ok"


def test_a2_cost_reconcile_records_observe_mode_meta(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(
        project_id="ref-cost",
        stage="analysis",
        agent="analysis",
        task_type="default",
        db_path=db_path,
    )

    entry_id = cost_tracker.reconcile(
        project_id="ref-cost",
        task_id=task_id,
        agent="analysis",
        tool="doubao_analyze",
        phase="analysis",
        cost_cny=0.42,
        tokens={"input": 100, "output": 40},
        model="doubao-turbo",
        shot_index=3,
        meta={"provider_request_id": "abc"},
        db_path=db_path,
    )
    totals = cost_tracker.get_project_cost("ref-cost", db_path=db_path)

    assert entry_id > 0
    assert totals["total_cost_cny"] == 0.42
    assert totals["entry_count"] == 1
    with queue.get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM cost_entries WHERE entry_id = ?", (entry_id,)).fetchone()

    assert row["tool"] == "doubao_analyze"
    assert row["operation"] == "reconcile"
    assert row["phase"] == "analysis"
    assert row["amount_cny"] == 0.42
    meta = cost_tracker.loads_meta(row["meta_json"])
    assert meta["budget_mode"] == "observe"
    assert meta["tokens"] == {"input": 100, "output": 40}
    assert meta["model"] == "doubao-turbo"
    assert meta["shot_index"] == 3
    assert meta["provider_request_id"] == "abc"

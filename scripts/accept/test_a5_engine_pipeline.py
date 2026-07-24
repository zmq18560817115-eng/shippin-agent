from __future__ import annotations

import json
from pathlib import Path

import pytest

from libshared import checkpoint
from orchestrator import engine, queue
from scripts.accept.accept_common import approve_take_gate_and_final_review


def test_a5_mock_pipeline_runs_with_two_human_gates(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "ref-e2e"
    queue.init_db(db_path=db_path)

    engine.start_pipeline(
        "ref-e2e",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )
    first_stop = engine.run_until_blocked("ref-e2e", db_path=db_path, run_root=run_root, mock=True)

    assert first_stop.status == "awaiting_human"
    assert first_stop.stage == "script_gate"
    assert checkpoint.read_latest("ref-e2e", run_root=run_root)["stage"] == "script_gate"

    engine.approve_gate("ref-e2e", "script_gate", approver="qa", db_path=db_path, run_root=run_root)
    second_stop = engine.run_until_blocked("ref-e2e", db_path=db_path, run_root=run_root, mock=True)

    assert second_stop.status == "awaiting_human"
    assert second_stop.stage == "hero_gate"

    engine.approve_gate("ref-e2e", "hero_gate", approver="qa", db_path=db_path, run_root=run_root)
    take_stop = engine.run_until_blocked("ref-e2e", db_path=db_path, run_root=run_root, mock=True)
    assert take_stop.stage == "take_gate"
    assert take_stop.status == "awaiting_human"
    approve_take_gate_and_final_review("ref-e2e", run_root=run_root, db_path=db_path)
    done = engine.run_until_blocked("ref-e2e", db_path=db_path, run_root=run_root, mock=True)

    assert done.status == "succeeded"
    assert done.stage == "archive"
    assert (run_root / "artifacts" / "analysis_report.json").is_file()
    assert (run_root / "artifacts" / "script_copy.json").is_file()
    assert (run_root / "artifacts" / "shot_plan.json").is_file()
    assert (run_root / "artifacts" / "asset_manifest.json").is_file()
    assert (run_root / "artifacts" / "render_report.json").is_file()
    assert (run_root / "artifacts" / "publish_archive.json").is_file()
    assert queue.list_tasks(status="failed", db_path=db_path) == []


def test_a5_take_gate_validation_failure_leaves_gate_recoverable(tmp_path: Path) -> None:
    db_path = tmp_path / "agentflow.db"
    run_root = tmp_path / "runs" / "ref-takegate"
    queue.init_db(db_path=db_path)

    engine.start_pipeline("ref-takegate", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("ref-takegate", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("ref-takegate", "script_gate", approver="qa", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("ref-takegate", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("ref-takegate", "hero_gate", approver="qa", db_path=db_path, run_root=run_root)
    take_stop = engine.run_until_blocked("ref-takegate", db_path=db_path, run_root=run_root, mock=True)
    assert take_stop.stage == "take_gate" and take_stop.status == "awaiting_human"

    # Approving before any take is selected must fail the selection check WITHOUT
    # advancing the gate state; otherwise the run deadlocks (gate marked succeeded
    # but no compose task queued, and no longer re-approvable).
    with pytest.raises(ValueError):
        engine.approve_gate("ref-takegate", "take_gate", approver="qa", db_path=db_path, run_root=run_root)

    gate = checkpoint._latest_for_stage("ref-takegate", "take_gate", run_root=run_root)
    assert gate is not None and gate["status"] == "awaiting_human"
    assert not [t for t in queue.list_tasks(project_id="ref-takegate", db_path=db_path) if t.stage == "compose"]

    # Selecting takes then re-approving must recover cleanly and queue compose.
    manifest_path = run_root / "artifacts" / "take_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for shot in manifest["shots"]:
        take = shot["takes"][0]
        take["status"] = "selected"
        shot["selected_take_id"] = take["take_id"]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    engine.approve_gate("ref-takegate", "take_gate", approver="qa", db_path=db_path, run_root=run_root)
    compose_tasks = [t for t in queue.list_tasks(project_id="ref-takegate", db_path=db_path) if t.stage == "compose"]
    assert len(compose_tasks) == 1


def test_a5_seedance_failure_isolated_and_retry_only_failed_shot(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    first_root = tmp_path / "runs" / "ref-shotfail"
    second_root = tmp_path / "runs" / "ref-other"
    queue.init_db(db_path=db_path)

    engine.start_pipeline("ref-shotfail", product_id="便携恒温杯", db_path=db_path, run_root=first_root, mock=True)
    engine.start_pipeline("ref-other", product_id="便携恒温杯", db_path=db_path, run_root=second_root, mock=True)

    engine.run_until_blocked("ref-shotfail", db_path=db_path, run_root=first_root, mock=True)
    engine.approve_gate("ref-shotfail", "script_gate", approver="qa", db_path=db_path, run_root=first_root)
    engine.run_until_blocked("ref-shotfail", db_path=db_path, run_root=first_root, mock=True)
    engine.approve_gate("ref-shotfail", "hero_gate", approver="qa", db_path=db_path, run_root=first_root)

    monkeypatch.setenv("SEEDANCE_MOCK_FAIL", "shot3")
    failed = engine.run_until_blocked("ref-shotfail", db_path=db_path, run_root=first_root, mock=True)

    assert failed.status == "failed"
    assert failed.stage == "production"
    shot_tasks = [
        task
        for task in queue.list_tasks(db_path=db_path)
        if task.project_id == "ref-shotfail" and task.stage == "production"
    ]
    assert len(shot_tasks) == 5
    failed_tasks = [task for task in shot_tasks if task.status == "failed"]
    succeeded_tasks = [task for task in shot_tasks if task.status == "succeeded"]
    assert [task.payload_json["shot_index"] for task in failed_tasks] == [3]
    assert sorted(task.payload_json["shot_index"] for task in succeeded_tasks) == [1, 2, 4, 5]
    assert not any(task.stage == "compose" for task in queue.list_tasks(db_path=db_path) if task.project_id == "ref-shotfail")

    other = engine.run_until_blocked("ref-other", db_path=db_path, run_root=second_root, mock=True)
    assert other.status == "awaiting_human"
    assert other.stage == "script_gate"

    monkeypatch.delenv("SEEDANCE_MOCK_FAIL", raising=False)
    retried = engine.retry_failed_shot("ref-shotfail", 3, db_path=db_path, run_root=first_root, mock=True)
    assert retried.status == "succeeded"
    assert retried.stage == "production"
    take_stop = engine.run_until_blocked("ref-shotfail", db_path=db_path, run_root=first_root, mock=True)
    assert take_stop.stage == "take_gate"
    approve_take_gate_and_final_review("ref-shotfail", run_root=first_root, db_path=db_path)
    all_done = engine.run_until_blocked("ref-shotfail", db_path=db_path, run_root=first_root, mock=True)

    assert all_done.status == "succeeded"
    assert all_done.stage == "archive"
    shot_tasks_after = [
        task
        for task in queue.list_tasks(db_path=db_path)
        if task.project_id == "ref-shotfail" and task.stage == "production"
    ]
    attempts_by_shot = {task.payload_json["shot_index"]: task.attempt for task in shot_tasks_after}
    assert attempts_by_shot == {1: 1, 2: 1, 3: 2, 4: 1, 5: 1}

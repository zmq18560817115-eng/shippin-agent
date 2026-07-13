from __future__ import annotations

from pathlib import Path

from libshared import checkpoint
from orchestrator import engine, queue


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

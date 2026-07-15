from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import engine, queue
from orchestrator.api import app


def test_manual_production_requires_hero_gate(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "gate-required"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("gate-required", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("gate-required", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("gate-required", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("gate-required", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/manual/run",
            json={"project_id": "gate-required", "stage": "production", "shot_index": 1, "mock": True},
        )

    assert response.status_code == 409
    assert "关键帧确认" in response.json()["detail"]


def test_archived_project_allows_shot_edit_and_manual_storyboard_run(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "manual-demo"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline(
        "manual-demo",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )
    engine.run_until_blocked("manual-demo", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate(
        "manual-demo", "script_gate", approver="test", db_path=db_path, run_root=run_root
    )
    engine.run_until_blocked("manual-demo", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate(
        "manual-demo", "hero_gate", approver="test", db_path=db_path, run_root=run_root
    )
    engine.run_until_blocked("manual-demo", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        shot_plan = client.get("/api/v2/artifacts/manual-demo/shot_plan").json()
        shot_plan["shots"][0]["visual"] = "Operator corrected visual"
        saved = client.put("/api/v2/artifacts/manual-demo/shot_plan", json=shot_plan)
        rerun = client.post(
            "/api/v2/manual/run",
            json={"project_id": "manual-demo", "stage": "storyboard", "mock": True},
        )

    assert saved.status_code == 200
    assert saved.json()["stale_sections"] == [1]
    assert rerun.status_code == 200
    assert rerun.json()["engine"]["stage"] == "hero_gate"
    assert rerun.json()["engine"]["status"] == "awaiting_human"


def test_manual_production_stops_before_compose(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "manual-shot"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline(
        "manual-shot",
        product_id="便携恒温杯",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )
    engine.run_until_blocked("manual-shot", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate(
        "manual-shot", "script_gate", approver="test", db_path=db_path, run_root=run_root
    )
    engine.run_until_blocked("manual-shot", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate(
        "manual-shot", "hero_gate", approver="test", db_path=db_path, run_root=run_root
    )
    stale_compose_id = queue.enqueue_task(
        project_id="manual-shot",
        stage="compose",
        agent="media",
        payload={"run_root": run_root.as_posix(), "revision": "stale"},
        db_path=db_path,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/manual/run",
            json={"project_id": "manual-shot", "stage": "production", "shot_index": 1, "mock": True},
        )

    assert response.status_code == 200
    assert response.json()["engine"]["stage"] == "production"
    assert response.json()["engine"]["status"] == "succeeded"
    tasks = queue.list_tasks(project_id="manual-shot", db_path=db_path)
    stale_compose = queue.get_task(stale_compose_id, db_path=db_path)
    assert stale_compose.status == "queued"
    assert not any(
        task.stage == "compose" and task.payload_json.get("revision") != "stale"
        for task in tasks
    )


def test_finished_project_can_be_deleted_without_deleting_shared_materials(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    queue.ensure_project("delete-me", product_id="恒温杯", db_path=db_path)
    (runs_root / "delete-me").mkdir(parents=True)

    with TestClient(app) as client:
        response = client.delete("/api/v2/pipeline/delete-me")
        missing = client.get("/api/v2/pipeline/delete-me")

    assert response.status_code == 200
    assert missing.status_code == 404
    assert not (runs_root / "delete-me").exists()

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import engine, queue
from orchestrator.api import app


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

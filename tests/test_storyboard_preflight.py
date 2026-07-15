from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import engine, queue
from orchestrator.api import app


def test_hero_gate_blocks_unsafe_storyboard_prompt(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "preflight-demo"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("preflight-demo", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("preflight-demo", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("preflight-demo", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("preflight-demo", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        plan = client.get("/api/v2/artifacts/preflight-demo/shot_plan").json()
        plan["shots"][0]["seedance_prompt"] = "Product appearance must match the white-background hero reference."
        plan["shots"][0]["visual_prompt"] = plan["shots"][0]["seedance_prompt"]
        assert client.put("/api/v2/artifacts/preflight-demo/shot_plan", json=plan).status_code == 200
        response = client.post(
            "/api/v2/gates/approve",
            json={"project_id": "preflight-demo", "stage": "hero_gate", "approver": "test", "mock": True},
        )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["message"] == "分镜安全预检未通过"
    assert detail["errors"][0]["shot_index"] == 1
    assert "场景与人物连续性" in detail["errors"][0]["missing"]

from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import engine, queue
from orchestrator.api import app


def test_generate_two_takes_and_select_one_for_compose(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "take-demo"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("take-demo", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("take-demo", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("take-demo", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("take-demo", db_path=db_path, run_root=run_root, mock=True)

    with TestClient(app) as client:
        take_a = client.post(
            "/api/v2/manual/run",
            json={"project_id": "take-demo", "stage": "production", "shot_index": 1, "take_id": "A", "mock": True},
        )
        take_b = client.post(
            "/api/v2/manual/run",
            json={"project_id": "take-demo", "stage": "production", "shot_index": 1, "take_id": "B", "mock": True},
        )
        selected = client.post(
            "/api/v2/takes/select",
            json={"project_id": "take-demo", "shot_index": 1, "take_id": "B"},
        )

    assert take_a.status_code == 200, take_a.text
    assert take_b.status_code == 200, take_b.text
    assert selected.status_code == 200, selected.text
    manifest = selected.json()["take_manifest"]
    assert manifest["shots"][0]["selected_take_id"] == "B"
    assert len(manifest["shots"][0]["takes"]) == 2
    report_shot = selected.json()["shot_report"]["shots"][0]
    assert report_shot["take_id"] == "B"
    assert report_shot["path"].endswith("shot-001-take-b.mp4")

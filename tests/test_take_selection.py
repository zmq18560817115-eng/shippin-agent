import json
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
    engine.approve_gate("take-demo", "hero_gate", approver="test", db_path=db_path, run_root=run_root)

    with TestClient(app) as client:
        take_a = client.post(
            "/api/v2/manual/run",
            json={"project_id": "take-demo", "stage": "production", "shot_index": 1, "take_id": "A", "mock": True},
        )
        take_b = client.post(
            "/api/v2/manual/run",
            json={"project_id": "take-demo", "stage": "production", "shot_index": 1, "take_id": "B", "mock": True},
        )
        rejected = client.post(
            "/api/v2/takes/select",
            json={"project_id": "take-demo", "shot_index": 1, "take_id": "B"},
        )
        manifest = json.loads((run_root / "artifacts" / "take_manifest.json").read_text(encoding="utf-8"))
        take_b_path = next(item for item in manifest["shots"][0]["takes"] if item["take_id"] == "B")["path"]
        output = run_root / take_b_path
        assert output.is_file()
        reviewed = client.post(
            "/api/v2/takes/review",
            json={
                "project_id": "take-demo",
                "shot_index": 1,
                "take_id": "B",
                "product_identity": True,
                "no_invented_brand": True,
                "temperature_display": True,
                "usage_flow": True,
                "continuity": True,
            },
        )
        selected = client.post(
            "/api/v2/takes/select",
            json={"project_id": "take-demo", "shot_index": 1, "take_id": "B"},
        )
        rereviewed = client.post(
            "/api/v2/takes/review",
            json={
                "project_id": "take-demo",
                "shot_index": 1,
                "take_id": "B",
                "product_identity": True,
                "no_invented_brand": True,
                "temperature_display": True,
                "usage_flow": True,
                "continuity": True,
                "notes": "复检通过：产品外观、98°F、倒液方向和连续性正确。",
            },
        )
        displayed = client.get("/api/v2/artifacts/take-demo/take_manifest")

    assert take_a.status_code == 200, take_a.text
    assert take_b.status_code == 200, take_b.text
    assert rejected.status_code == 409, rejected.text
    assert reviewed.status_code == 200, reviewed.text
    assert selected.status_code == 200, selected.text
    assert rereviewed.status_code == 200, rereviewed.text
    assert displayed.status_code == 200, displayed.text
    manifest = selected.json()["take_manifest"]
    assert manifest["shots"][0]["selected_take_id"] == "B"
    assert len(manifest["shots"][0]["takes"]) == 2
    report_shot = selected.json()["shot_report"]["shots"][0]
    assert report_shot["take_id"] == "B"
    assert report_shot["path"].endswith("shot-001-take-b.mp4")
    assert displayed.json()["shots"][0]["takes"][0]["playable"] is True
    assert displayed.json()["shots"][0]["takes"][0]["media_url"]
    displayed_take_b = next(item for item in displayed.json()["shots"][0]["takes"] if item["take_id"] == "B")
    assert displayed_take_b["status"] == "selected"
    assert displayed_take_b["qa"]["notes"].startswith("复检通过")


def test_rejecting_a_selected_take_clears_selection(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "selected-reject"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("selected-reject", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("selected-reject", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("selected-reject", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("selected-reject", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("selected-reject", "hero_gate", approver="test", db_path=db_path, run_root=run_root)

    with TestClient(app) as client:
        client.post("/api/v2/manual/run", json={"project_id": "selected-reject", "stage": "production", "shot_index": 1, "take_id": "A", "mock": True})
        client.post(
            "/api/v2/takes/review",
            json={"project_id": "selected-reject", "shot_index": 1, "take_id": "A", "product_identity": True, "no_invented_brand": True, "temperature_display": True, "usage_flow": True, "continuity": True},
        )
        client.post("/api/v2/takes/select", json={"project_id": "selected-reject", "shot_index": 1, "take_id": "A"})
        rejected = client.post(
            "/api/v2/takes/review",
            json={"project_id": "selected-reject", "shot_index": 1, "take_id": "A", "product_identity": False, "no_invented_brand": True, "temperature_display": True, "usage_flow": True, "continuity": True, "notes": "产品外观不一致，需要重做。"},
        )

    shot = rejected.json()["take_manifest"]["shots"][0]
    assert rejected.status_code == 200
    assert rejected.json()["approved"] is False
    assert shot["selected_take_id"] is None
    assert shot["takes"][0]["status"] == "rejected"


def test_automated_visual_block_cannot_be_overridden_by_positive_manual_checks(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "automated-block"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("automated-block", product_id="便携恒温杯", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("automated-block", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("automated-block", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("automated-block", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("automated-block", "hero_gate", approver="test", db_path=db_path, run_root=run_root)

    with TestClient(app) as client:
        client.post("/api/v2/manual/run", json={"project_id": "automated-block", "stage": "production", "shot_index": 1, "take_id": "A", "mock": True})
        path = run_root / "artifacts" / "take_manifest.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["shots"][0]["takes"][0]["automated_visual_qa"] = {
            "status": "BLOCKED",
            "summary": "OCR 识别到 98°C",
        }
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        reviewed = client.post(
            "/api/v2/takes/review",
            json={"project_id": "automated-block", "shot_index": 1, "take_id": "A", "product_identity": True, "no_invented_brand": True, "temperature_display": True, "usage_flow": True, "continuity": True},
        )

    take = reviewed.json()["take_manifest"]["shots"][0]["takes"][0]
    assert reviewed.status_code == 200
    assert reviewed.json()["approved"] is False
    assert take["status"] == "rejected"
    assert take["qa"]["blocked_by_automation"] is True


def test_hero_approval_generates_initial_take_and_waits_for_selection(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "agentflow.db"
    runs_root = tmp_path / "runs"
    run_root = runs_root / "selection-gate"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    queue.init_db(db_path)
    engine.start_pipeline("selection-gate", product_id="thermos", db_path=db_path, run_root=run_root, mock=True)
    engine.run_until_blocked("selection-gate", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("selection-gate", "script_gate", approver="test", db_path=db_path, run_root=run_root)
    engine.run_until_blocked("selection-gate", db_path=db_path, run_root=run_root, mock=True)
    engine.approve_gate("selection-gate", "hero_gate", approver="test", db_path=db_path, run_root=run_root)
    status = engine.run_until_blocked("selection-gate", db_path=db_path, run_root=run_root, mock=True)

    manifest = json.loads((run_root / "artifacts" / "take_manifest.json").read_text(encoding="utf-8"))
    tasks = queue.list_tasks(project_id="selection-gate", db_path=db_path)
    assert status.stage == "take_gate"
    assert status.status == "awaiting_human"
    assert len(manifest["shots"]) == 5
    assert all(shot["takes"][0]["take_id"] == "A" for shot in manifest["shots"])
    assert not any(task.stage == "compose" and task.status == "queued" for task in tasks)

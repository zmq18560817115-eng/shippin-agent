import json
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator.api import app
from tools.collect import manual_import


def test_tiktok_intake_runs_to_script_gate_in_mock_mode(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "queue.db"
    runs_root = tmp_path / "runs"
    library_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(runs_root))
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/collect/tiktok/run",
            json={
                "url": "https://www.tiktok.com/@demo/video/99887766",
                "product_id": "便携恒温杯",
                "transcript_text": "A 30 second temperature display product demonstration.",
                "mock": True,
            },
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["engine"]["stage"] == "script_gate"
    assert payload["capture"]["transcript_source"] == "operator"
    assert payload["warnings"] == []
    meta = manual_import.load_material_meta(payload["material"]["material_id"], library_root)
    assert meta["processing_status"] == "analyzed"
    assert meta["source_mode"] == "mock"
    assert meta["transcript_text"].startswith("A 30 second")
    assert json.loads(meta["ai_analysis_json"])["analysis"]["hook_3s"]
    project_root = runs_root / payload["project_id"]
    assert (project_root / "artifacts" / "research_brief.json").exists()
    assert (project_root / "artifacts" / "strategy_brief.json").exists()
    assert (project_root / "artifacts" / "script_breakdown.json").exists()

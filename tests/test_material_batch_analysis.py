from fastapi.testclient import TestClient

from orchestrator.api import app
from tools.collect import manual_import


def test_batch_material_analysis_updates_selected_items_without_creating_projects(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    db_path = tmp_path / "batch.db"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    imported = manual_import.import_links(
        [{"url": "https://www.tiktok.com/@demo/video/991", "caption": "夜间恒温杯准备", "transcript_text": "夜间使用恒温杯准备奶液。"}],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        response = client.post("/api/v2/collect/materials/batch-analyze", json={"material_ids": [material_id], "mock": True})
        assert response.status_code == 200, response.text
        assert response.json()["completed"] == [material_id]
        assert client.get("/api/v2/pipeline").json()["items"] == []

    meta = manual_import.load_material_meta(material_id, library_root)
    assert meta["processing_status"] == "analyzed"
    assert "hook_3s" in meta["ai_analysis_json"]


def test_batch_material_analysis_reports_missing_transcript(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "batch-missing.db"))
    imported = manual_import.import_links(
        [{"url": "https://www.tiktok.com/@demo/video/992"}],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        response = client.post("/api/v2/collect/materials/batch-analyze", json={"material_ids": [material_id], "mock": True})
        assert response.status_code == 200
        assert response.json()["completed"] == []
        assert response.json()["failures"][0]["message"] == "缺少转写或简介"

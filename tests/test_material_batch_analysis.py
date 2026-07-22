from fastapi.testclient import TestClient

from orchestrator.api import app
from orchestrator import queue
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
        assert response.json()["failures"][0]["message"] == "缺少真实字幕或 ASR 转写；视频简介不能代替内容转写"


def test_standalone_analysis_accepts_library_material_and_writes_back_report(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone-analysis.db"))
    monkeypatch.setenv("VAF_RUN_ROOT", str(tmp_path / "runs"))
    imported = manual_import.import_links(
        [{
            "url": "https://www.tiktok.com/@demo/video/995",
            "caption": "恒温杯夜间冲奶",
            "transcript_text": "凌晨两点准备奶液，先把奶液倒入恒温杯，再从圆形出液口倒入干净奶瓶。",
        }],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"action": "analysis", "source_material_id": material_id, "mock": True},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["artifact_name"] == "analysis_report"
        assert payload["meta"]["source_mode"] == "material_library"
        assert payload["meta"]["source_material_id"] == material_id
        download = client.get(payload["download_url"])
        assert download.status_code == 200

    meta = manual_import.load_material_meta(material_id, library_root)
    assert meta["processing_status"] == "analyzed"
    assert (library_root / material_id / "analysis_report.json").is_file()
    assert "hook_3s" in meta["ai_analysis_json"]


def test_standalone_material_analysis_requires_transcript(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone-missing.db"))
    imported = manual_import.import_links(
        [{"url": "https://www.tiktok.com/@demo/video/996", "caption": "只有简介"}],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"action": "analysis", "source_material_id": material_id, "mock": True},
        )
        assert response.status_code == 422
        assert "缺少字幕或 ASR 转写" in response.json()["detail"]


def test_standalone_research_accepts_library_material(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "standalone-research.db"))
    monkeypatch.setenv("VAF_RUN_ROOT", str(tmp_path / "runs"))
    imported = manual_import.import_links(
        [{
            "url": "https://www.tiktok.com/@demo/video/997",
            "caption": "恒温杯竞品参考",
            "transcript_text": "开场展示夜间准备痛点，随后演示恒温杯操作，结尾提醒收藏。",
        }],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={"action": "research", "source_material_id": material_id, "mock": True},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["artifact_name"] == "research_brief"
        assert payload["meta"]["source_mode"] == "material_library"
        assert payload["meta"]["source_material_id"] == material_id
        assert material_id in payload["artifact"]["source_refs"]


def test_batch_material_quarantine_restore_and_delete(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "governance.db"))
    imported = manual_import.import_links(
        [{"url": "https://www.tiktok.com/@demo/video/993", "caption": "恒温杯素材"}],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        quarantined = client.post("/api/v2/collect/materials/batch-action", json={"material_ids": [material_id], "action": "quarantine", "reason": "画面不相关"})
        assert quarantined.status_code == 200
        library = client.get("/api/v2/collect/library").json()
        assert library["items"][0]["material_meta"]["production_readiness"]["lane"] == "quarantine"
        restored = client.post("/api/v2/collect/materials/batch-action", json={"material_ids": [material_id], "action": "restore"})
        assert restored.status_code == 200
        assert manual_import.load_material_meta(material_id, library_root)["processing_status"] == "raw"
        deleted = client.post("/api/v2/collect/materials/batch-action", json={"material_ids": [material_id], "action": "delete"})
        assert deleted.status_code == 200
        assert not (library_root / material_id).exists()
        assert manual_import.load_library_index(library_root)["items"] == []


def test_batch_delete_refuses_material_referenced_by_project(monkeypatch, tmp_path):
    library_root = tmp_path / "materials"
    db_path = tmp_path / "referenced.db"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(library_root))
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    imported = manual_import.import_links(
        [{"url": "https://www.tiktok.com/@demo/video/994", "caption": "恒温杯素材"}],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=library_root,
    )
    material_id = imported["items"][0]["material_id"]
    queue.init_db(db_path=db_path)
    queue.ensure_project("uses-material", payload={"source_material_id": material_id}, db_path=db_path)

    with TestClient(app) as client:
        response = client.post("/api/v2/collect/materials/batch-action", json={"material_ids": [material_id], "action": "delete"})
        assert response.status_code == 200
        assert response.json()["completed"] == []
        assert "已被项目引用" in response.json()["failures"][0]["message"]
        assert (library_root / material_id / "material_meta.json").is_file()

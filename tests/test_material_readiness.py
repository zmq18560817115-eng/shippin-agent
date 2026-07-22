from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import api
from orchestrator.api import app
from tools.collect import manual_import


def test_material_readiness_requires_complete_relevant_local_asset(tmp_path: Path) -> None:
    material_dir = tmp_path / "tt-1"
    material_dir.mkdir()
    (material_dir / "source.mp4").write_bytes(b"video")
    (material_dir / "cover.jpg").write_bytes(b"cover")
    meta = {
        "video_title": "便携恒温杯夜间喂养演示",
        "source_keyword": "恒温杯 夜间喂养",
        "local_video_path": "source.mp4",
        "local_cover_path": "cover.jpg",
        "transcript_text": "完整中文转写",
        "ai_analysis_json": '{"analysis":{"hook_3s":"夜间准备","structure":["钩子","证明"],"shot_breakdown":[{"shot_index":1}]}}',
    }

    result = api._material_production_readiness(meta, material_dir)

    assert result["ready"] is True
    assert result["lane"] == "production"
    assert result["relevance_score"] == 1.0
    assert result["checks"] == {"video": True, "cover": True, "transcript": True, "breakdown": True}


def test_material_readiness_quarantines_metadata_only_or_irrelevant_asset(tmp_path: Path) -> None:
    result = api._material_production_readiness(
        {"video_title": "QR code tutorial", "source_keyword": "恒温杯", "processing_status": "metadata_only"},
        tmp_path,
    )

    assert result["ready"] is False
    assert result["lane"] == "quarantine"
    assert "与采集关键词不匹配" in result["missing"]
    assert "未下载原视频" in result["missing"]
    assert "缺少转写" in result["missing"]


def test_material_readiness_keeps_relevant_incomplete_asset_in_processing(tmp_path: Path) -> None:
    result = api._material_production_readiness(
        {"video_title": "便携恒温杯夜间喂养", "source_keyword": "恒温杯", "processing_status": "captured"},
        tmp_path,
    )

    assert result["ready"] is False
    assert result["lane"] == "processing"
    assert "与采集关键词不匹配" not in result["missing"]


def test_material_readiness_uses_persisted_discovery_relevance(tmp_path: Path) -> None:
    result = api._material_production_readiness(
        {
            "video_title": "generic title without query words",
            "source_keyword": "恒温杯",
            "discovery_relevance": {"score": 0.82, "relevant": True},
        },
        tmp_path,
    )

    assert result["relevance_score"] == 0.82
    assert result["lane"] == "processing"
    assert "与采集关键词不匹配" not in result["missing"]


def test_material_readiness_rejects_capture_metadata_without_real_breakdown(tmp_path: Path) -> None:
    result = api._material_production_readiness(
        {
            "video_title": "便携恒温杯演示",
            "source_keyword": "恒温杯",
            "ai_analysis_json": '{"capture_status":"downloaded","frame_paths":["frame-01.jpg"]}',
        },
        tmp_path,
    )

    assert result["ready"] is False
    assert "缺少镜头拆解" in result["missing"]


def test_pipeline_rejects_material_that_has_not_passed_admission(tmp_path: Path, monkeypatch) -> None:
    material_root = tmp_path / "materials"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(material_root))
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "agentflow.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    imported = manual_import.import_links(
        [{"url": "https://www.tiktok.com/@demo/video/7000000000000000123", "title": "QR code tutorial"}],
        product_id="便携恒温杯",
        source_keyword="恒温杯",
        library_root=material_root,
    )
    material_id = imported["items"][0]["material_id"]

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/pipeline/run",
            json={"project_id": "blocked-material", "product_id": "便携恒温杯", "source_material_id": material_id, "mock": True},
        )

    assert response.status_code == 409
    assert "隔离区" in response.json()["detail"]
    assert "与采集关键词不匹配" in response.json()["detail"]


def test_corrupted_take_note_is_detected() -> None:
    assert api._looks_corrupted_text("??????????98?F????") is True
    assert api._looks_corrupted_text("产品外观正确，温度显示为 98°F。") is False

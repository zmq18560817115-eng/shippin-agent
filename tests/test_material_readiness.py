from pathlib import Path

from orchestrator import api


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
        "ai_analysis_json": '{"analysis":{"hook_3s":"夜间准备"}}',
    }

    result = api._material_production_readiness(meta, material_dir)

    assert result["ready"] is True
    assert result["lane"] == "production"
    assert result["relevance_score"] == 1.0


def test_material_readiness_quarantines_metadata_only_or_irrelevant_asset(tmp_path: Path) -> None:
    result = api._material_production_readiness(
        {"video_title": "QR code tutorial", "source_keyword": "恒温杯", "processing_status": "metadata_only"},
        tmp_path,
    )

    assert result["ready"] is False
    assert result["lane"] == "cleanup"
    assert "与采集关键词不匹配" in result["missing"]
    assert "未下载原视频" in result["missing"]
    assert "缺少转写" in result["missing"]


def test_corrupted_take_note_is_detected() -> None:
    assert api._looks_corrupted_text("??????????98?F????") is True
    assert api._looks_corrupted_text("产品外观正确，温度显示为 98°F。") is False

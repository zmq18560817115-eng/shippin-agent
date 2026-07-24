import json
from pathlib import Path

from orchestrator import engine, queue
from tools.collect import manual_import


def test_reference_video_is_analysis_only_by_default(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("VAF_ALLOW_REFERENCE_FOOTAGE_IN_OUTPUT", raising=False)
    shot_plan = {
        "shots": [
            {"number": 1, "footage_type": "AI_VIDEO"},
            {"number": 2, "footage_type": "AI_VIDEO"},
        ]
    }

    result = engine._attach_reference_footage("missing-project", shot_plan, db_path=tmp_path / "agentflow.db")

    assert result["shots"][1]["footage_type"] == "AI_VIDEO"
    assert "reference_path" not in result["shots"][1]


def test_selected_tiktok_material_seeds_pipeline_analysis(monkeypatch, tmp_path: Path) -> None:
    material_root = tmp_path / "materials"
    run_root = tmp_path / "runs" / "reference-seeded"
    db_path = tmp_path / "agentflow.db"
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(material_root))
    imported = manual_import.import_links(
        [{
            "url": "https://www.tiktok.com/@creator/video/123456789",
            "caption": "高热度户外喂养参考",
            "transcript_text": "开场先展示公园里手忙脚乱的准备，再用快速动作完成喂养。",
            "play_count": 880000,
        }],
        product_id="便携恒温杯",
        source_keyword="portable bottle warmer",
        library_root=material_root,
    )
    material_id = imported["items"][0]["material_id"]
    reference_report = {
        "version": "2.0",
        "project_id": f"material-{material_id}",
        "source_link_id": None,
        "material_meta_ref": material_id,
        "hook_3s": "公园长椅前，准备动作突然被宝宝哭声打断。",
        "structure": ["突发打断", "动作受阻", "找到方案", "快速完成", "轻松收束"],
        "voiceover_text": "原视频通过突发打断建立钩子，再以快速动作完成转折。",
        "pacing": [
            {"start_s": 0, "end_s": 6, "role": "钩子"},
            {"start_s": 6, "end_s": 12, "role": "痛点"},
            {"start_s": 12, "end_s": 18, "role": "方案"},
            {"start_s": 18, "end_s": 24, "role": "证明"},
            {"start_s": 24, "end_s": 30, "role": "行动号召"},
        ],
        "keyframes": ["动作被打断", "快速转折"],
        "shot_breakdown": [
            {
                "number": index,
                "timing": f"{(index - 1) * 6}-{index * 6}s",
                "visual": f"参考镜头 {index}",
                "action": f"参考动作 {index}",
                "purpose": role,
                "transition": "动作匹配转场",
            }
            for index, role in enumerate(["钩子", "痛点", "方案", "证明", "行动号召"], start=1)
        ],
        "fingerprint": "selected-reference-test",
    }
    (material_root / material_id / "analysis_report.json").write_text(
        json.dumps(reference_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    queue.init_db(db_path=db_path)
    engine.start_pipeline(
        "reference-seeded",
        product_id="便携恒温杯",
        source_material_id=material_id,
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )

    stopped = engine.run_until_blocked(
        "reference-seeded",
        db_path=db_path,
        run_root=run_root,
        mock=True,
    )

    assert stopped.stage == "script_gate"
    project_analysis = json.loads((run_root / "artifacts" / "analysis_report.json").read_text(encoding="utf-8"))
    assert project_analysis["hook_3s"] == reference_report["hook_3s"]
    assert project_analysis["shot_breakdown"] == reference_report["shot_breakdown"]
    assert project_analysis["reference_provenance"]["source_material_id"] == material_id

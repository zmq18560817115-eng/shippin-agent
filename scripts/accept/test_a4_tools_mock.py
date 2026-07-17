from __future__ import annotations

from pathlib import Path

from libshared import artifacts
from tools import tool_registry
from tools.base_tool import ToolContext


WHITE_HERO = "data/01_素材库/产品资料/便携恒温杯/listing-0602-nw/主图/白底主图.png"


def test_a4_registry_contains_block4_tools() -> None:
    expected = {
        "volcengine_asr",
        "doubao_analyze",
        "doubao_script",
        "doubao_shotplan",
        "doubao_review",
        "claude_script",
        "hero_frame",
        "seedance_shot",
        "ffmpeg_compose",
    }

    assert expected.issubset(set(tool_registry.list_tools()))


def test_a4_mock_tool_chain_returns_valid_artifacts(tmp_path: Path) -> None:
    context = {"mock": True, "run_root": str(tmp_path / "ref-a4")}
    asr = tool_registry.execute_tool("volcengine_asr", {"audio_path": "inputs/source.mp4"}, context=context)
    assert asr.ok
    assert asr.cost_cny == 0
    assert asr.meta["mock"] is True

    analysis = tool_registry.execute_tool(
        "doubao_analyze",
        {"project_id": "ref-a4", "transcript_text": asr.data["transcript_text"]},
        context=context,
    )
    assert analysis.ok
    artifacts.validate_artifact("analysis_report", analysis.data["analysis_report"])

    script = tool_registry.execute_tool(
        "doubao_script",
        {
            "project_id": "ref-a4",
            "product_id": "便携恒温杯",
            "analysis_report": analysis.data["analysis_report"],
        },
        context=context,
    )
    assert script.ok
    script_copy = script.data["script_copy"]
    artifacts.validate_artifact("script_copy", script_copy)

    shotplan = tool_registry.execute_tool(
        "doubao_shotplan",
        {"project_id": "ref-a4", "script_copy": script_copy},
        context=context,
    )
    assert shotplan.ok
    shot_plan = shotplan.data["shot_plan"]
    artifacts.validate_artifact("shot_plan", shot_plan, script_copy=script_copy)

    review = tool_registry.execute_tool(
        "doubao_review",
        {"project_id": "ref-a4", "script_copy": script_copy},
        context=context,
    )
    assert review.ok
    artifacts.validate_artifact("review_report", review.data["review_report"])

    hero = tool_registry.execute_tool(
        "hero_frame",
        {
            "project_id": "ref-a4",
            "product_id": "便携恒温杯",
            "shot_plan": shot_plan,
            "seedance_source": WHITE_HERO,
        },
        context=context,
    )
    assert hero.ok
    asset_manifest = hero.data["asset_manifest"]
    artifacts.validate_artifact("asset_manifest", asset_manifest)

    shot = tool_registry.execute_tool(
        "seedance_shot",
        {
            "project_id": "ref-a4",
            "shot": shot_plan["shots"][0],
            "asset_manifest": asset_manifest,
        },
        context=context,
    )
    assert shot.ok
    assert Path(shot.data["path"]).is_file()
    assert shot.data["shot_report"]["shots"][0]["status"] == "succeeded"
    artifacts.validate_artifact("shot_report", shot.data["shot_report"])

    render = tool_registry.execute_tool(
        "ffmpeg_compose",
        {
            "project_id": "ref-a4",
            "shot_report": shot.data["shot_report"],
            "script_copy": script_copy,
        },
        context=context,
    )
    assert render.ok
    assert Path(render.data["output_path"]).is_file()
    artifacts.validate_artifact("render_report", render.data["render_report"])


def test_a4_real_tool_without_key_reports_not_configured() -> None:
    result = tool_registry.execute_tool(
        "doubao_script",
        {"project_id": "ref-a4", "product_id": "便携恒温杯"},
        context={"mock": False, "env": {}},
    )

    assert not result.ok
    assert result.error["category"] == "not_configured"


def test_a4_explicit_empty_environment_does_not_inherit_process_secrets() -> None:
    context = ToolContext.from_mapping({"mock": False, "env": {}})

    assert context.env == {}

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from libshared import artifacts
from libshared.paths import ROOT
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


@register_tool("seedance_shot")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "SEEDANCE_API_KEY")
    project_id = str(payload.get("project_id") or "ref-mock")
    shot = payload.get("shot") or {}
    asset_manifest = payload.get("asset_manifest") or {}
    artifacts.validate_artifact("asset_manifest", asset_manifest)
    number = int(shot.get("number") or payload.get("shot_index") or 1)

    fail_selector = str(context.env.get("SEEDANCE_MOCK_FAIL", ""))
    if context.mock and fail_selector in {str(number), f"shot{number}", f"shot-{number}"}:
        return ToolResult.failure(
            "provider_error",
            f"mock SeedDance failure for shot {number}",
            meta={"tool": "seedance_shot", "mock": True, "shot_index": number},
        )

    run_root = context.run_root or (ROOT / "data" / "runs" / project_id)
    shots_dir = run_root / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    output = shots_dir / f"shot-{number:03d}.mp4"
    if context.mock:
        output.write_bytes(b"mock seedance mp4\n")
        provider_meta = {"provider": "mock"}
    else:
        provider_meta = ark.create_seedance_video(
            context,
            prompt=_shot_prompt(shot, asset_manifest),
            image_path=str(asset_manifest.get("seedance_source") or ""),
            output_path=output,
            duration_sec=_duration_sec(shot),
        )

    shot_report = {
        "version": "2.0",
        "project_id": project_id,
        "shots": [
            {
                "number": number,
                "status": "succeeded",
                "path": output.as_posix(),
                "cost_cny": context.pricing_for("seedance_shot") if not context.mock else 0.0,
                "attempt": int(payload.get("attempt") or 1),
            }
        ],
    }
    artifacts.validate_artifact("shot_report", shot_report)
    return ToolResult.success(
        {"path": output.as_posix(), "shot_report": shot_report},
        cost_cny=shot_report["shots"][0]["cost_cny"],
        meta={
            "tool": "seedance_shot",
            "mock": context.mock,
            "shot_index": number,
            "seedance_source": asset_manifest.get("seedance_source"),
            **provider_meta,
        },
    )


def _shot_prompt(shot: dict[str, Any], asset_manifest: dict[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            str(shot.get("seedance_prompt") or shot.get("visual_prompt") or shot.get("visual") or ""),
            f"Seedance source: {asset_manifest.get('seedance_source')}",
        )
        if part
    )


def _duration_sec(shot: dict[str, Any]) -> int:
    camera = shot.get("camera_motion") if isinstance(shot.get("camera_motion"), dict) else {}
    try:
        return max(3, min(10, int(float(camera.get("duration_sec") or 5))))
    except (TypeError, ValueError):
        return 5

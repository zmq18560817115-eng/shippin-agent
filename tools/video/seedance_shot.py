from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from libshared import artifacts
from libshared.paths import ROOT
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.collect import product_library
from tools.tool_registry import register_tool
from tools.video.ffmpeg_compose import write_mock_video
from tools.video.media_validation import is_playable_mp4


@register_tool("seedance_shot")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "SEEDANCE_API_KEY")
    project_id = str(payload.get("project_id") or "ref-mock")
    shot = payload.get("shot") or {}
    asset_manifest = payload.get("asset_manifest") or {}
    artifacts.validate_artifact("asset_manifest", asset_manifest)
    number = int(shot.get("number") or payload.get("shot_index") or 1)
    take_id = str(payload.get("take_id") or "").strip()

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
    suffix = f"-take-{take_id.casefold()}" if take_id else ""
    output = shots_dir / f"shot-{number:03d}{suffix}.mp4"
    reference_path = Path(str(shot.get("reference_path") or ""))
    if not context.mock and is_playable_mp4(output):
        provider_meta = {"provider": "existing_media_recovery", "reused_path": output.as_posix()}
    elif reference_path.is_file():
        output = reference_path
        provider_meta = {"provider": "reference_video", "reference_path": reference_path.as_posix()}
    elif context.mock:
        write_mock_video(output, _duration_sec(shot))
        provider_meta = {"provider": "mock"}
    else:
        provider_meta = ark.create_seedance_video(
            context,
            prompt=_shot_prompt(shot, asset_manifest),
            image_path=str(asset_manifest.get("seedance_source") or ""),
            image_paths=[
                str(path)
                for path in (shot.get("reference_paths") or asset_manifest.get("reference_paths") or [])
                if str(path)
            ],
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
                "duration_sec": _duration_sec(shot),
                **({"take_id": take_id} if take_id else {}),
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
            "take_id": take_id or None,
            "seedance_source": asset_manifest.get("seedance_source"),
            "reference_paths": shot.get("reference_paths") or asset_manifest.get("reference_paths") or [],
            **provider_meta,
        },
    )


def _shot_prompt(shot: dict[str, Any], asset_manifest: dict[str, Any]) -> str:
    product_facts = product_library.product_guardrail_text(str(asset_manifest.get("product_id") or ""))
    return " ".join(
        part
        for part in (
            str(shot.get("seedance_prompt") or shot.get("visual_prompt") or shot.get("visual") or ""),
            f"Seedance source: {asset_manifest.get('seedance_source')}",
            f"Approved product facts and hard constraints: {product_facts}" if product_facts else "",
            "Use only the approved product identity from the reference image. Do not add any invented brand name, logo, watermark, label, or readable text. Do not replace the product with a generic bottle or another brand.",
            "For a warming-cup pouring shot: pour liquid from the warming cup spout into a separate clean baby bottle; never place the baby bottle inside the warming cup and never pour in the reverse direction.",
            "The single required action must visibly complete on camera: keep the main lid closed, tilt the warming cup, show one continuous liquid stream leaving the approved round spout, and show that stream entering the separate baby bottle. Do not open the main lid, do not merely place the products side by side, and do not end before the pour is visible.",
            "If the display is visible, show exactly 98°F with the Fahrenheit symbol; never show Celsius or 98°C.",
        )
        if part
    )


def _duration_sec(shot: dict[str, Any]) -> int:
    camera = shot.get("camera_motion") if isinstance(shot.get("camera_motion"), dict) else {}
    try:
        return max(3, min(10, int(float(camera.get("duration_sec") or 5))))
    except (TypeError, ValueError):
        return 5

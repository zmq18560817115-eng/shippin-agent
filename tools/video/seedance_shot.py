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
from tools.video.visual_qa import extract_review_frames, inspect_review_frames


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
        reference_paths = _reference_paths_for_shot(shot, asset_manifest)
        provider_meta = ark.create_seedance_video(
            context,
            prompt=_shot_prompt(shot, asset_manifest),
            image_path=str(asset_manifest.get("seedance_source") or ""),
            image_paths=[
                str(path)
                for path in reference_paths
                if str(path)
            ],
            output_path=output,
            duration_sec=_duration_sec(shot),
        )

    review_frames: list[Path] = []
    automated_visual_qa: dict[str, Any] = {
        "version": "1.0",
        "status": "NEEDS_REVIEW",
        "engine": "not_run_in_mock" if context.mock else "not_available",
        "checks": {"no_forbidden_celsius": True, "valid_98f_detected": False, "frames_sampled": 0},
        "summary": "演练模式保留人工质检。" if context.mock else "未能抽取单镜质检帧，必须人工复核。",
        "frames": [],
    }
    if not context.mock and is_playable_mp4(output):
        review_frames = extract_review_frames(
            output,
            run_root / "take_review_frames" / f"shot-{number:03d}-take-{take_id or 'default'}",
        )
        automated_visual_qa = inspect_review_frames(
            [path.as_posix() for path in review_frames],
            product_id=str(asset_manifest.get("product_id") or ""),
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
                "review_frame_paths": [path.as_posix() for path in review_frames],
                "automated_visual_qa": automated_visual_qa,
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
            "reference_paths": _reference_paths_for_shot(shot, asset_manifest),
            **provider_meta,
        },
    )


def _shot_prompt(shot: dict[str, Any], asset_manifest: dict[str, Any]) -> str:
    product_facts = product_library.product_guardrail_text(str(asset_manifest.get("product_id") or ""))
    identity_mode = str(asset_manifest.get("identity_mode") or "product_reference")
    if identity_mode == "prompt_only":
        return " ".join(
            part
            for part in (
                str(
                    shot.get("seedance_prompt_zh")
                    or shot.get("seedance_prompt")
                    or shot.get("visual_prompt")
                    or shot.get("visual_zh")
                    or shot.get("visual")
                    or ""
                ),
                "Pure Prompt creative mode: follow only the requested subject, scene, action, camera, lighting, and style.",
                "Do not introduce a warming cup, baby bottle, milk-pouring action, temperature display, or unrelated branded product unless the user explicitly requested it.",
                "Do not add invented logos, watermarks, subtitles, overlays, or readable text.",
            )
            if part
        )
    number = int(shot.get("number") or 0)
    if number == 3:
        action_rule = (
            "Shot 3 action only: open the warming cup and pour liquid from an approved source into the cup interior. "
            "Do not pour from the cup into a baby bottle in this shot. Do not show the final dispensing action."
        )
    elif number == 4:
        action_rule = (
            "Shot 4 action only: close and lock the main screw-on lid before pouring, with the main lid visibly closed throughout the action. The small dust cover may open only enough to expose the approved round spout, while the main lid stays locked. "
            "Tilt the warming cup and show one continuous liquid stream leaving only through that round spout and entering a separate clean, completely unbranded baby bottle. "
            "Never pour through the open main mouth, never reverse the direction, and never place the bottle inside the cup."
        )
    else:
        action_rule = (
            f"Shot {number} must not contain pouring, flowing liquid, an open main lid, or a bottle inserted into the cup. "
            "Keep the product closed and perform only the single scene action described for this shot."
        )
    return " ".join(
        part
        for part in (
            str(
                shot.get("seedance_prompt_zh")
                or shot.get("seedance_prompt")
                or shot.get("visual_prompt")
                or shot.get("visual_zh")
                or shot.get("visual")
                or ""
            ),
            f"Seedance source: {asset_manifest.get('seedance_source')}",
            f"Approved product facts and hard constraints: {product_facts}" if product_facts else "",
            "Use only the approved product identity from the reference image. Preserve its exact body shape, lid, handle, controls, color, and approved logo. Do not add any invented brand name, logo, watermark, label, subtitle, overlay, or readable text. The separate baby bottle must be transparent and completely unbranded. Do not replace the product with a generic bottle or another brand.",
            "Character continuity contract for every shot: people may appear naturally when the approved script calls for them. Preserve the same approved adult caregiver identity, face, age range, hairstyle, wardrobe, sleeves, hands, body proportions, and relationship to the product across shots. Do not introduce a different performer, distorted anatomy, or unexplained identity changes. Product-only and hands-only framing may still be used when it best serves the approved shot, but it is not mandatory.",
            "For a warming-cup pouring shot: pour liquid from the warming cup spout into a separate clean baby bottle; never place the baby bottle inside the warming cup and never pour in the reverse direction.",
            action_rule,
            "Display contract: only show a lit display when the shot explicitly requires a temperature proof close-up. In every other shot the screen must remain fully unlit, blank, or outside the readable crop, with no digits or unit glyphs. In a temperature proof shot it must read exactly 98°F with one Fahrenheit symbol and no Celsius symbol. Never show °C, 98°C, 90°C, mixed °C/F, extra digits, or corrupted glyphs. If exact 98°F cannot be rendered, keep the display unlit or fully out of frame.",
        )
        if part
    )


def _duration_sec(shot: dict[str, Any]) -> int:
    camera = shot.get("camera_motion") if isinstance(shot.get("camera_motion"), dict) else {}
    try:
        return max(3, min(10, int(float(camera.get("duration_sec") or 5))))
    except (TypeError, ValueError):
        return 5


def _reference_paths_for_shot(shot: dict[str, Any], asset_manifest: dict[str, Any]) -> list[str]:
    explicit = [str(path) for path in shot.get("reference_paths") or [] if str(path)]
    if explicit:
        return explicit
    shot_text = " ".join(
        str(shot.get(key) or "")
        for key in ("visual", "visual_zh", "visual_prompt", "seedance_prompt", "seedance_prompt_zh")
    ).casefold()
    selected: list[str] = []
    for path in asset_manifest.get("reference_paths") or []:
        path_text = str(path)
        name = Path(path_text).stem.casefold()
        is_pour_reference = any(token in name for token in ("倒出", "出液", "pour", "spout"))
        shot_has_pour = (
            any(token in shot_text for token in ("倒入", "倒液", "出液口", "pour", "spout"))
            and any(token in shot_text for token in ("奶瓶", "baby bottle"))
        )
        if is_pour_reference and shot_has_pour:
            selected.append(path_text)
    return selected

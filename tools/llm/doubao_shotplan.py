from __future__ import annotations

from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.llm.mock_artifacts import mock_script_copy, mock_shot_plan
from tools.providers import ark
from tools.collect import product_library
from tools.tool_registry import register_tool


@register_tool("doubao_shotplan")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
        return _execute_real(payload, context)
    project_id = str(payload.get("project_id") or "ref-mock")
    script_copy = payload.get("script_copy") or mock_script_copy(project_id)
    product_facts = product_library.product_guardrail_text(str(script_copy.get("product_id") or ""))
    shot_plan = mock_shot_plan(project_id, script_copy)
    artifacts.validate_artifact("shot_plan", shot_plan, script_copy=script_copy)
    return ToolResult.success(
        {"shot_plan": shot_plan},
        cost_cny=context.pricing_for("doubao_shotplan") if not context.mock else 0.0,
        meta={"tool": "doubao_shotplan", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    script_copy = payload.get("script_copy") or mock_script_copy(project_id)
    product_facts = product_library.product_guardrail_text(str(script_copy.get("product_id") or ""))
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You create traceable, continuous AI video shot plans. Return strict JSON only. "
                    "Use one stable scene and one stable caregiver profile across all shots. "
                    "Every shot must continue the previous action and lock product appearance to the approved white-background hero reference."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create shot_plan JSON with one shot per script section, vertical 9:16. "
                    "Return shots plus scene_continuity and character_continuity. For every shot include visual, visual_prompt, "
                    "seedance_prompt, and camera_motion.type. Keep the same location, lighting, wardrobe, hands, props, "
                    "product color, lid, spout, display, button, proportions, and logo placement. Build a visible action sequence: "
                    "establish the feeding-prep scene, show the pain, introduce the separate warming cup, demonstrate the approved "
                    "pouring flow, then finish with a product CTA. Never place a whole baby bottle inside the cup. "
                    "If the display is visible it must read 98 degrees Fahrenheit (98 F), never Celsius. Script: "
                    f"{script_copy}. Approved product facts and hard constraints: {product_facts or 'not provided'}"
                ),
            },
        ],
    )
    shot_plan = {
        "version": "2.0",
        "project_id": project_id,
        "script_copy_ref": "artifacts/script_copy.json",
        "aspect_ratio": "9:16",
        "shots": _normalize_shots(
            response.get("shots"),
            script_copy,
            scene_continuity=str(response.get("scene_continuity") or "one stable night feeding-prep scene"),
            character_continuity=str(response.get("character_continuity") or "same caregiver, wardrobe, hands, and props"),
        ),
    }
    artifacts.validate_artifact("shot_plan", shot_plan, script_copy=script_copy)
    return ToolResult.success(
        {"shot_plan": shot_plan},
        cost_cny=context.pricing_for("doubao_shotplan"),
        meta={"tool": "doubao_shotplan", "mock": False, **meta},
    )


def _normalize_shots(
    value: Any,
    script_copy: dict[str, Any],
    *,
    scene_continuity: str = "one stable feeding-prep scene",
    character_continuity: str = "same caregiver, wardrobe, hands, and props",
) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    motions = ("dolly_in", "static", "pan_right")
    shots: list[dict[str, Any]] = []
    for index, section in enumerate(script_copy.get("sections") or [], start=1):
        item = raw[index - 1] if index - 1 < len(raw) and isinstance(raw[index - 1], dict) else {}
        role = str(section.get("role") or "")
        visual = str(item.get("visual") or _fallback_visual(index, role))
        prompt = str(item.get("seedance_prompt") or item.get("visual_prompt") or visual)
        prompt = _lock_prompt(
            prompt,
            str(section.get("voiceover_en") or ""),
            shot_index=index,
            scene_continuity=scene_continuity,
            character_continuity=character_continuity,
        )
        motion_value = item.get("camera_motion", {}).get("type") if isinstance(item.get("camera_motion"), dict) else ""
        shots.append(
            {
                "number": int(section.get("number") or index),
                "visual": visual,
                "visual_prompt": str(item.get("visual_prompt") or visual),
                "seedance_prompt": prompt,
                "footage_type": "AI_VIDEO",
                "camera_motion": {
                    "type": _motion_type(str(motion_value or motions[min(index - 1, len(motions) - 1)])),
                    "duration_sec": 6,
                },
            }
        )
    return shots


def _lock_prompt(
    prompt: str,
    voiceover: str,
    *,
    shot_index: int = 1,
    scene_continuity: str = "one stable feeding-prep scene",
    character_continuity: str = "same caregiver, wardrobe, hands, and props",
) -> str:
    lock = (
        "Continuity lock: same location and lighting across all five shots; "
        f"scene: {scene_continuity}; character: {character_continuity}. "
        "Product identity lock: match the approved white-background hero reference exactly; preserve body proportions, "
        "purple lid and ring, round pouring spout, vertical temperature display, oval power button, logo placement, and charging-port cover. "
        "The warming cup and baby bottle are separate products. Never insert or attach a bottle, nipple, carton, or commercial milk bottle to the cup. "
        "When visible, the display reads 98 degrees Fahrenheit (98 F), never Celsius. "
        f"Action continuity for shot {shot_index}: {_shot_action(shot_index)} "
    )
    prompt = " ".join(prompt.strip().split())
    prompt = lock + prompt
    if voiceover:
        prompt = f"{prompt} Voiceover context: {voiceover}"
    return prompt


def _fallback_visual(index: int, role: str) -> str:
    visuals = {
        1: "Establish one night feeding-prep scene with the approved warming cup visible on the nightstand.",
        2: "The same caregiver prepares an approved milk source while the separate clean baby bottle waits nearby.",
        3: "Close-up: the same hands open the warming cup and pour milk into the cup interior without inserting a bottle.",
        4: "Close-up: tilt the warming cup and pour through the round spout into the separate clean baby bottle; show 98 F only if legible.",
        5: "Return to the same scene for a stable product-and-caregiver CTA composition with the approved cup identity clear.",
    }
    return f"{role}: {visuals.get(index, visuals[5])}"


def _shot_action(index: int) -> str:
    return {
        1: "establish the scene and product position; no unexplained motion.",
        2: "continue in the same scene and show the preparation problem without changing people or props.",
        3: "continue the same hand movement; open the cup and pour from an approved source into the cup.",
        4: "continue from heating/preparation; tilt the cup and pour through its round spout into a separate clean baby bottle.",
        5: "settle the product back into the established scene and hold a clean final CTA frame.",
    }.get(index, "continue the previous action without a scene or identity change.")


def _motion_type(value: str) -> str:
    allowed = {"dolly_in", "dolly_out", "pan_left", "pan_right", "static", "arc", "crash_zoom"}
    return value if value in allowed else "static"

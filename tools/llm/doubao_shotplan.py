from __future__ import annotations

import re
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
                    "You create concise, continuous AI video shot plans. Return strict JSON only. "
                    "Keep one stable scene and one stable caregiver profile across all shots. "
                    "Shots are generated independently and hard to match, so make transitions smooth: "
                    "each shot must OPEN on framing, subject position and lighting that continue the PREVIOUS shot's "
                    "closing frame, and camera moves must stay slow and in a consistent direction so cuts do not jump. "
                    "Do not repeat product safety locks: the production system adds them deterministically. "
                    "All Chinese fields (visual_zh, seedance_prompt_zh) must be written in Simplified Chinese."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create a compact JSON object with scene_continuity, character_continuity, and exactly five shots in vertical 9:16. "
                    "For every shot return only visual, visual_zh, seedance_prompt, seedance_prompt_zh, and camera_motion.type. "
                    "In each shot's seedance_prompt, briefly state the opening frame so it matches the previous shot's ending "
                    "(same subject placement and camera angle) for a seamless transition. Prefer gentle camera moves "
                    "(slow push-in or slow pan) over static-to-moving jumps. "
                    "Keep every text field below 45 words; do not restate global continuity or product rules inside each shot. "
                    "Use this five-beat sequence: establish feeding-prep scene, show the pain, introduce the separate warming cup, "
                    "demonstrate the pour, then finish with a product CTA. Script sections: "
                    f"{_shotplan_input(script_copy)}. Product facts: {(product_facts or 'not provided')[:900]}"
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


def _shotplan_input(script_copy: dict[str, Any]) -> list[dict[str, str]]:
    """Keep real model input bounded; deterministic guards are added after generation."""
    return [
        {
            "number": str(section.get("number") or index),
            "timing": str(section.get("timing") or ""),
            "role": str(section.get("role") or ""),
            "scene": str(section.get("scene_zh") or "")[:260],
            "action": str(section.get("action_zh") or "")[:260],
            "story": str(section.get("story_beat_zh") or "")[:180],
        }
        for index, section in enumerate((script_copy.get("sections") or [])[:5], start=1)
    ]


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
        visual = _clean_temperature_text(str(item.get("visual") or _fallback_visual(index, role)))
        visual_prompt = _clean_temperature_text(str(item.get("visual_prompt") or visual))
        # The two directional product-use shots are deterministic safety beats.
        # Free-form model copy is retained for the other three shots only.
        safety_fallback = index in {3, 4}
        if safety_fallback:
            visual = _fallback_visual(index, role)
            visual_prompt = visual
        prompt = visual_prompt if safety_fallback else _clean_temperature_text(str(item.get("seedance_prompt") or visual_prompt or visual))
        prompt = _lock_prompt(
            prompt,
            str(section.get("voiceover_zh") or section.get("voiceover_en") or ""),
            shot_index=index,
            scene_continuity=scene_continuity,
            character_continuity=character_continuity,
        )
        motion_value = item.get("camera_motion", {}).get("type") if isinstance(item.get("camera_motion"), dict) else ""
        shots.append(
            {
                "number": int(section.get("number") or index),
                "visual": visual,
                "visual_prompt": visual_prompt,
                "seedance_prompt": prompt,
                "visual_zh": _fallback_visual_zh(index) if safety_fallback else str(item.get("visual_zh") or _fallback_visual_zh(index)),
                "seedance_prompt_zh": _fallback_prompt_zh(index) if safety_fallback else str(item.get("seedance_prompt_zh") or _fallback_prompt_zh(index)),
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
    prompt = " ".join(prompt.strip().split())
    # Idempotent: never stack the safety lock if the prompt already carries it
    # (e.g. re-saving an edited shot plan). The lock is a hard product-identity
    # requirement, so it is always guaranteed on the seedance_prompt.
    if "white-background hero" in prompt.casefold():
        return prompt
    lock = (
        "Continuity lock: same location and lighting across all five shots; "
        f"scene: {scene_continuity}; character: {character_continuity}. "
        "Product identity lock: match the approved white-background hero reference exactly; preserve body proportions, "
        "purple lid and ring, round pouring spout, vertical temperature display, oval power button, logo placement, and charging-port cover. "
        "Keep the product clearly lit and fully visible; even in the night scene a warm bedside lamp evenly illuminates the product, avoid an all-black or underexposed frame. "
        "The warming cup and baby bottle are separate products. Never insert or attach a bottle, nipple, carton, or commercial milk bottle to the cup. "
        "When visible, the display reads 98 degrees Fahrenheit (98 F), never Celsius. "
        f"Action continuity for shot {shot_index}: {_shot_action(shot_index)} "
    )
    prompt = lock + prompt
    if voiceover and shot_index not in {3, 4}:
        prompt = f"{prompt} Voiceover context: {voiceover}"
    return prompt


def ensure_shot_locks(shot_plan: dict, script_copy: dict | None = None) -> dict:
    """Guarantee every shot's seedance_prompt carries the product-identity lock.

    Applied when a shot plan is saved so edits or older generations can never
    strip the safety constraint (which would otherwise deadlock the hero gate).
    """
    sections = (script_copy or {}).get("sections") or []
    for index, shot in enumerate(shot_plan.get("shots") or [], start=1):
        if not isinstance(shot, dict):
            continue
        voiceover = ""
        if index - 1 < len(sections) and isinstance(sections[index - 1], dict):
            voiceover = str(sections[index - 1].get("voiceover_en") or "")
        shot["seedance_prompt"] = _lock_prompt(
            str(shot.get("seedance_prompt") or shot.get("visual_prompt") or shot.get("visual") or ""),
            voiceover,
            shot_index=index,
        )
    return shot_plan


def _fallback_visual(index: int, role: str) -> str:
    visuals = {
        1: "Establish one night feeding-prep scene with the approved warming cup visible on the nightstand.",
        2: "The same caregiver prepares an approved milk source while the separate clean baby bottle waits nearby.",
        3: "Close-up: the same hands open the warming cup and pour milk into the cup interior without inserting a bottle.",
        4: "Close-up: tilt the warming cup and pour through the round spout into the separate clean baby bottle; show 98 F only if legible.",
        5: "Return to the same scene for a stable product-and-caregiver CTA composition with the approved cup identity clear.",
    }
    return visuals.get(index, visuals[5])


def _fallback_visual_zh(index: int) -> str:
    return {
        1: "夜间喂养准备场景，恒温杯放在床头柜上。",
        2: "同一位照护者准备允许的奶液来源，干净奶瓶在旁等待。",
        3: "特写：打开恒温杯，将奶液倒入杯体内部，不放入整只奶瓶。",
        4: "特写：倾斜恒温杯，经圆形杯嘴倒入独立干净奶瓶；如显示温度，仅为 98 华氏度。",
        5: "回到同一夜间场景，清晰展示产品并完成行动号召。",
    }.get(index, "保持同一场景和产品外观。")


def _fallback_prompt_zh(index: int) -> str:
    return (
        "连续性锁定：同一卧室、暖光、照护者、服装、手部和道具。产品外观严格匹配已批准白底主图；"
        "恒温杯与奶瓶为独立产品，禁止将奶瓶插入杯内；出现温度时只能显示 98 华氏度，禁止摄氏度。"
        f"镜头 {index}：{_fallback_visual_zh(index)}"
    )


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


def _clean_temperature_text(value: str) -> str:
    value = re.sub(r"98[^A-Za-z0-9\s]{1,5}F", "98 F", value, flags=re.IGNORECASE)
    return value.replace("98°F", "98 F").replace("98 F degrees", "98 degrees Fahrenheit")


def _has_outbound_pour(value: str) -> bool:
    lowered = value.casefold()
    return "pour" in lowered and "spout" in lowered and "baby bottle" in lowered

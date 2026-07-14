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
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You create traceable AI video shot plans. Return strict JSON only. "
                    "Every AI shot prompt must lock product appearance to the white-background hero reference."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create shot_plan JSON with one shot per script section, vertical 9:16. "
                    "Use product-only, hands-only, bedside or travel-parent scenes. "
                    "Do not show a whole baby bottle inserted into the cup. Script: "
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
        "shots": _normalize_shots(response.get("shots"), script_copy),
    }
    artifacts.validate_artifact("shot_plan", shot_plan, script_copy=script_copy)
    return ToolResult.success(
        {"shot_plan": shot_plan},
        cost_cny=context.pricing_for("doubao_shotplan"),
        meta={"tool": "doubao_shotplan", "mock": False, **meta},
    )


def _normalize_shots(value: Any, script_copy: dict[str, Any]) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    motions = ("dolly_in", "static", "pan_right")
    shots: list[dict[str, Any]] = []
    for index, section in enumerate(script_copy.get("sections") or [], start=1):
        item = raw[index - 1] if index - 1 < len(raw) and isinstance(raw[index - 1], dict) else {}
        role = str(section.get("role") or "")
        visual = str(item.get("visual") or f"{role} shot with portable warming cup in a safe feeding-prep scene.")
        prompt = str(item.get("seedance_prompt") or item.get("visual_prompt") or visual)
        prompt = _lock_prompt(prompt, str(section.get("voiceover_en") or ""))
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
                    "duration_sec": 5,
                },
            }
        )
    return shots


def _lock_prompt(prompt: str, voiceover: str) -> str:
    lock = (
        "Product appearance must match the white-background hero reference. "
        "Use the white-background hero as the only product identity source. "
        "No bottle inserted into the cup. "
    )
    prompt = " ".join(prompt.strip().split())
    if "white-background hero" not in prompt.casefold() and "product appearance must match" not in prompt.casefold():
        prompt = lock + prompt
    if voiceover:
        prompt = f"{prompt} Voiceover context: {voiceover}"
    return prompt


def _motion_type(value: str) -> str:
    allowed = {"dolly_in", "dolly_out", "pan_left", "pan_right", "static", "arc", "crash_zoom"}
    return value if value in allowed else "static"

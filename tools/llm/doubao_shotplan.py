from __future__ import annotations

import re
from typing import Any

from libshared import artifacts
from libshared.agent_contracts import agent_system_prompt
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
    rewrite_reason = str(payload.get("rewrite_reason") or "").strip()
    fallback_plan = mock_shot_plan(project_id, script_copy)
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    agent_system_prompt("storyboard")
                    + "你负责把一个连续故事设计成可执行的竖屏镜头，而不是生成五张孤立产品图。只返回严格 JSON。"
                    "保持同一场景、同一照护者、同一服装与道具关系。每个镜头开场必须承接上一个镜头结束时的主体位置、动作方向和光线。"
                    "先在内部完成全片视觉节奏设计，再写逐镜结果。产品安全锁由系统确定性追加，不要在每镜重复堆砌。"
                    "visual_zh 与 seedance_prompt_zh 必须使用简体中文。"
                ),
            },
            {
                "role": "user",
                "content": (
                    "创建包含 scene_continuity、character_continuity 和五个 9:16 竖屏镜头的紧凑 JSON。"
                    "每镜只返回 visual、visual_zh、seedance_prompt、seedance_prompt_zh 和 camera_motion.type。"
                    "先给五镜分配不同视觉任务：建立空间、表现冲突、发现方案、看清关键动作、情绪收束。至少使用三种景别或运镜，禁止五镜同构图。"
                    "每镜只设计一个主要动作，并写清主体在画面中的位置、景别、机位高度、光线、前后景关系和镜头结束状态。"
                    "每个 seedance_prompt_zh 必须按顺序写清：场景环境、主体位置、产品动作、景别与镜头焦段、机位与运镜、光线、连续性锚点、禁止项、镜头结束状态。"
                    "下一镜开场要继承上一镜的主体位置、动作方向与视线；运镜以缓慢推近、平移或拉远为主，避免跳轴和无动机炫技。"
                    "提示词必须具体可见，禁止使用高级感、氛围感、电影感等空词代替画面设计；不得要求字幕、配文、标语、标签、Logo 或其他可读文字。"
                    "每个文字字段保持简洁，不在逐镜重复全局产品规则。五镜依次完成喂养准备、等待痛点、独立恒温杯出现、正确倒液、产品与人物共同收束。"
                    f"脚本段落：{_shotplan_input(script_copy)}。产品事实：{(product_facts or '未提供')[:900]}。"
                    f"必须修复的质量反馈：{rewrite_reason or '无'}。"
                    "交付前静默复看整条时间线：若镜头重复、转场不连续、动作不可生成或产品成为无意义摆拍，先重写再返回 JSON。"
                ),
            },
        ],
    )
    raw_shots = response.get("shots")
    scene_continuity = str(response.get("scene_continuity") or fallback_plan.get("scene_continuity") or "同一生活场景与光线")
    character_continuity = str(response.get("character_continuity") or fallback_plan.get("character_continuity") or "同一位照护者与服装道具")
    shot_plan = {
        "version": "2.0",
        "project_id": project_id,
        "script_copy_ref": "artifacts/script_copy.json",
        "aspect_ratio": "9:16",
        "scene_continuity": scene_continuity,
        "character_continuity": character_continuity,
        "shots": _normalize_shots(
            raw_shots,
            script_copy,
            scene_continuity=scene_continuity,
            character_continuity=character_continuity,
            fallback_shots=fallback_plan.get("shots") or [],
        ),
        "generation": {
            "provider": "ark",
            "model": str(meta.get("model") or "doubao"),
            "prompt_version": "storyboard-v2-input-aware-fallback",
            "structure_fallback_applied": not isinstance(raw_shots, list) or len(raw_shots) < 5,
        },
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
    fallback_shots: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    raw = value if isinstance(value, list) else []
    fallback_shots = fallback_shots or mock_shot_plan("fallback", script_copy).get("shots") or []
    motions = ("dolly_in", "static", "pan_right", "static", "dolly_out")
    shots: list[dict[str, Any]] = []
    for index, section in enumerate(script_copy.get("sections") or [], start=1):
        item = raw[index - 1] if index - 1 < len(raw) and isinstance(raw[index - 1], dict) else {}
        fallback = fallback_shots[index - 1] if index - 1 < len(fallback_shots) else {}
        role = str(section.get("role") or "")
        visual = _clean_temperature_text(str(item.get("visual") or fallback.get("visual") or _fallback_visual(index, role)))
        visual_prompt = _clean_temperature_text(str(item.get("visual_prompt") or fallback.get("visual_prompt") or visual))
        # The two directional product-use shots are deterministic safety beats.
        # Free-form model copy is retained for the other three shots only.
        safety_fallback = index in {3, 4}
        if safety_fallback:
            scenario_visual = str(fallback.get("visual") or "").strip()
            visual = _clean_temperature_text(
                f"{_fallback_visual(index, role)} Context from approved script: {scenario_visual}".strip()
            )
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
                "visual_zh": _clean_temperature_text(str(fallback.get("visual_zh") or _fallback_visual_zh(index))) if safety_fallback else _clean_temperature_text(_without_generated_text(str(item.get("visual_zh") or fallback.get("visual_zh") or _fallback_visual_zh(index)), index)),
                "seedance_prompt_zh": _clean_temperature_text(str(fallback.get("seedance_prompt_zh") or _fallback_prompt_zh(index))) if safety_fallback else _clean_temperature_text(_without_generated_text(str(item.get("seedance_prompt_zh") or fallback.get("seedance_prompt_zh") or _fallback_prompt_zh(index)), index)),
                "footage_type": "AI_VIDEO",
                "camera_motion": {
                    "type": _motion_type(str(motion_value or motions[min(index - 1, len(motions) - 1)])),
                    "duration_sec": 6,
                },
            }
        )
    if len({str((shot.get("camera_motion") or {}).get("type") or "") for shot in shots}) < 2:
        for index, shot in enumerate(shots):
            shot["camera_motion"]["type"] = motions[min(index, len(motions) - 1)]
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
    lowered_prompt = prompt.casefold()
    required_markers = ["continuity lock:", "product identity lock:", "separate products", "never insert"]
    display_markers = (
        ["temperature proof contract:", "fahrenheit", "never show celsius"]
        if shot_index in {4, 5}
        else ["not a temperature proof shot", "fully unlit", "do not render any digits"]
    )
    if all(marker in lowered_prompt for marker in [*required_markers, *display_markers]):
        return prompt
    display_contract = (
        "This shot is not a temperature proof shot. Keep the temperature display fully unlit, blank, "
        "or outside the readable crop; do not render any digits, temperature unit, or glowing symbols. "
        if shot_index not in {4, 5}
        else "Temperature proof contract: if the display is readable, it must show exactly 98 degrees "
        "Fahrenheit (98 F) with a single Fahrenheit symbol. Never show Celsius, 98 C, 90 C, mixed units, "
        "extra digits, or malformed glyphs. If exact 98 F cannot be rendered, keep the display unlit. "
    )
    lock = (
        "Continuity lock: same location and lighting across all five shots; "
        f"scene: {scene_continuity}; character: {character_continuity}. "
        "Product identity lock: match the approved white-background hero reference exactly; preserve body proportions, "
        "purple lid and ring, round pouring spout, vertical temperature display, oval power button, logo placement, and charging-port cover. "
        "Keep the product clearly lit and fully visible; even in the night scene a warm bedside lamp evenly illuminates the product, avoid an all-black or underexposed frame. "
        "The warming cup and baby bottle are separate products. Never insert or attach a bottle, nipple, carton, or commercial milk bottle to the cup. "
        f"{display_contract}"
        f"Action continuity for shot {shot_index}: {_shot_action(shot_index)} "
        f"Camera contract: {_shot_camera_contract(shot_index)} "
        "Negative constraints: no malformed hands, duplicated props, warped product body, unreadable display, invented accessories, jump cuts, or continuity breaks. "
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


def _shot_camera_contract(index: int) -> str:
    return {
        1: "24mm wide establishing frame at eye level, slow dolly in, end with the product anchored on the right third.",
        2: "50mm medium close-up at chest height, restrained lateral move, preserve the established screen direction.",
        3: "70mm hand-and-product close-up from slightly above, static support, end after liquid enters the cup.",
        4: "85mm macro close-up level with the round spout, gentle follow move, keep the outbound pour direction readable.",
        5: "35mm medium-wide closing frame at eye level, slow dolly out, hold a stable product-and-caregiver composition.",
    }.get(index, "50mm neutral framing at eye level with motivated, restrained movement.")


def _motion_type(value: str) -> str:
    allowed = {"dolly_in", "dolly_out", "pan_left", "pan_right", "static", "arc", "crash_zoom"}
    return value if value in allowed else "static"


def _clean_temperature_text(value: str) -> str:
    value = re.sub(r"98[^A-Za-z0-9\s]{1,5}F", "98 F", value, flags=re.IGNORECASE)
    return value.replace("98°F", "98 F").replace("98 F degrees", "98 degrees Fahrenheit")


def _without_generated_text(value: str, index: int) -> str:
    forbidden = ("配文", "字幕", "文字叠加", "屏幕文字", "标题文字", "slogan", "caption", "overlay text")
    return _fallback_visual_zh(index) if any(token in value.casefold() for token in forbidden) else value


def _has_outbound_pour(value: str) -> bool:
    lowered = value.casefold()
    return "pour" in lowered and "spout" in lowered and "baby bottle" in lowered

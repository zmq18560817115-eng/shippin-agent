from __future__ import annotations

import re
from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.llm.mock_artifacts import mock_script_copy
from tools.providers import ark
from tools.collect import product_library
from tools.tool_registry import register_tool


@register_tool("doubao_script")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
        return _execute_real(payload, context)
    project_id = str(payload.get("project_id") or "ref-mock")
    product_id = str(payload.get("product_id") or "便携恒温杯")
    script_copy = mock_script_copy(project_id, product_id, provider="doubao")
    artifacts.validate_artifact("script_copy", script_copy)
    return ToolResult.success(
        {"script_copy": script_copy},
        cost_cny=context.pricing_for("doubao_script") if not context.mock else 0.0,
        meta={"tool": "doubao_script", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    product_id = str(payload.get("product_id") or "便携恒温杯")
    analysis_report = payload.get("analysis_report") or {}
    strategy_brief = payload.get("strategy_brief") or {}
    rewrite_reason = str(payload.get("rewrite_reason") or "").strip()
    product_facts = product_library.product_guardrail_text(product_id)
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You write brand-safe TikTok scripts for baby product overseas localization. "
                    "Return strict JSON only. Avoid medical, guarantee, best, pain-free, and competitor claims."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create script_copy JSON for product_id "
                    f"{product_id}. Use exactly 5 sections with roles 钩子, 痛点, 方案, 证明, 行动号召 and continuous timings "
                    "0-6s, 6-12s, 12-18s, 18-24s, 24-30s. For every section return voiceover_en plus these Chinese operator fields: voiceover_zh, scene_zh (environment, lighting, props, character state), action_zh (visible action and product-use step), and story_beat_zh (what changes from the previous beat and why it advances the story). "
                    "The five sections must create one continuous, filmable story. Beat 1 establishes the scene; beat 2 shows the waiting problem; "
                    "beat 3 only pours an approved milk source into the warming cup; beat 4 only pours from the warming cup through its round spout into a separate clean baby bottle; beat 5 closes with a CTA. "
                    "Do not combine the two pouring directions in one beat. Product fact: portable warming cup is separate from baby bottle. "
                    f"Approved product facts and hard constraints: {product_facts or 'not provided'}. "
                    f"Previous review feedback that must be fixed: {rewrite_reason or 'none'}. "
                    f"Approved content strategy: {strategy_brief}. Analysis: {analysis_report}"
                ),
            },
        ],
    )
    sections = _normalize_sections(response.get("sections"))
    script_copy = {
        "version": "2.0",
        "project_id": project_id,
        "product_id": product_id,
        "source_link_id": analysis_report.get("source_link_id"),
        "total_duration_s": 30,
        "generator": {
            "provider": "ark",
            "model": str(meta.get("model") or "doubao"),
            "prompt_version": "real-ark-v1",
        },
        "sections": sections,
        "feedback_constraints_applied": _string_list(response.get("feedback_constraints_applied"), []),
    }
    artifacts.validate_artifact("script_copy", script_copy)
    return ToolResult.success(
        {"script_copy": script_copy},
        cost_cny=context.pricing_for("doubao_script"),
        meta={"tool": "doubao_script", "mock": False, **meta},
    )


def _normalize_sections(value: Any) -> list[dict[str, Any]]:
    defaults = [
        ("钩子", "0-6s", "Bottle prep should not take over your night."),
        ("痛点", "6-12s", "Cold milk and long waits can make late feeds harder."),
        ("方案", "12-18s", "Pour milk from the approved source into the warming cup."),
        ("证明", "18-24s", "When ready, pour through the round spout into a separate clean bottle."),
        ("行动号召", "24-30s", "Save this for calmer feeds at home or on the go."),
    ]
    raw = value if isinstance(value, list) else []
    sections: list[dict[str, Any]] = []
    for index, (role, timing, voiceover) in enumerate(defaults, start=1):
        item = raw[index - 1] if index - 1 < len(raw) and isinstance(raw[index - 1], dict) else {}
        line = _clean_voiceover(str(item.get("voiceover_en") or item.get("subtitle_en") or voiceover))
        chinese_line = str(item.get("voiceover_zh") or "").strip()
        sections.append(
            {
                "number": index,
                "role": role,
                "timing": timing,
                "voiceover_en": line,
                "voiceover_zh": chinese_line or _default_chinese_voiceover(index),
                "scene_zh": str(item.get("scene_zh") or _default_scene(index)),
                "action_zh": _default_action(index) if index in {3, 4} else str(item.get("action_zh") or _default_action(index)),
                "story_beat_zh": str(item.get("story_beat_zh") or _default_story_beat(index)),
                "subtitle_en": line,
                "selling_points": _string_list(item.get("selling_points"), []),
            }
        )
    return sections


def _clean_voiceover(value: str) -> str:
    text = " ".join(value.strip().split())
    replacements = {
        "pain-free": "gentler-feeling",
        "painless": "gentler-feeling",
        "increase milk supply": "fit feeding into your routine",
        "boost lactation": "fit feeding into your routine",
        "guaranteed": "designed",
        "never settle": "make room",
        "never": "",
        "always": "",
        "best": "useful",
        "#1": "useful",
        "FDA approved": "approved",
        "medical grade": "well-designed",
    }
    lowered = text.casefold()
    for forbidden, safe in replacements.items():
        if forbidden.casefold() in lowered:
            text = re.sub(re.escape(forbidden), safe, text, flags=re.IGNORECASE)
            text = " ".join(text.split())
            lowered = text.casefold()
    if text:
        text = text[:1].upper() + text[1:]
    return text[:220] or "Save this for calmer feeds at home or on the go."


def _default_chinese_voiceover(index: int) -> str:
    return {
        1: "夜间喂养准备，不必占满你的时间。",
        2: "奶液变冷和漫长等待，会让睡前准备更困难。",
        3: "将允许的奶液倒入恒温杯，开始恒温准备。",
        4: "准备好后，经圆形出液口倒入独立干净奶瓶。",
        5: "为下一次夜间喂养先收藏这条。",
    }.get(index, "为下一次夜间喂养先收藏这条。")


def _default_scene(index: int) -> str:
    return {
        1: "深夜卧室，暖黄色床头灯，床头柜上有恒温杯、干净奶瓶和已准备好的喂养用品；同一位照护者穿浅色家居服。",
        2: "保持同一卧室与暖光，照护者查看等待中的奶瓶，婴儿不入镜，仅以环境声和急切动作表达时间压力。",
        3: "同一床头柜台面，恒温杯与干净奶瓶并排摆放，产品白底身份图作为外观锚点。",
        4: "保持同一床头柜、人物、服装与暖光，独立干净奶瓶位于恒温杯出液口下方。",
        5: "回到整洁的床头柜全景，照护者放下准备完成的奶瓶，恒温杯置于画面前景。",
    }.get(index, "保持同一场景、人物、光线与产品外观。")


def _default_action(index: int) -> str:
    return {
        1: "照护者轻放恒温杯到床头柜，建立夜间喂养准备的真实场景。",
        2: "照护者看向等待中的奶液和奶瓶，停顿后开始准备，表现等待带来的不便。",
        3: "只展示将允许的奶液从独立容器倒入恒温杯内部；禁止在本镜头反向倒出，禁止把奶瓶插入杯中。",
        4: "只展示倾斜恒温杯，经圆形出液口将奶液倒入独立、干净的奶瓶；若显示温度，只能是 98°F。",
        5: "照护者轻松收好物品，镜头停留在产品与准备完成的奶瓶上，形成自然收束。",
    }.get(index, "以连续、可执行的产品使用动作推进画面。")


def _default_story_beat(index: int) -> str:
    return {
        1: "从夜间真实情境切入，让观众立刻识别自己熟悉的喂养时刻。",
        2: "把“准备麻烦”具体化，为产品出现建立合理动机。",
        3: "产品作为解决方案进入画面，先清楚展示奶液进入恒温杯的方向。",
        4: "承接上一动作，清楚证明奶液从恒温杯流向独立奶瓶的正确方向。",
        5: "回到平静有序的结果，给出低压力的收藏或了解更多引导。",
    }.get(index, "承接前一段并推进到下一段。")


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return fallback

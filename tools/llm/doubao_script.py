from __future__ import annotations

import re
from typing import Any

from libshared import artifacts
from libshared.agent_contracts import agent_system_prompt
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
    analysis_report = payload.get("analysis_report") or {}
    strategy_brief = payload.get("strategy_brief") or {}
    creative_request = " ".join(
        str(value).strip()
        for value in (
            strategy_brief.get("content_direction"),
            analysis_report.get("voiceover_text"),
            analysis_report.get("hook_3s"),
        )
        if str(value or "").strip()
    )
    script_copy = mock_script_copy(
        project_id,
        product_id,
        provider="doubao",
        creative_request=creative_request,
    )
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
                    agent_system_prompt("script")
                ),
            },
            {
                "role": "user",
                "content": (
                    f"为产品 {product_id} 创作 script_copy JSON。先在内部比较三个真实生活切口，只输出最有张力且最可拍的一版。"
                    "必须使用钩子、痛点、方案、证明、行动号召五段，时间依次为 0-6s、6-12s、12-18s、18-24s、24-30s。"
                    "每段返回 voiceover_zh、scene_zh、action_zh、story_beat_zh。scene_zh 必须包含具体环境、光线、道具位置和人物当下状态；"
                    "action_zh 只写镜头中可以看见的一个主要动作；story_beat_zh 必须说明这一段相对上一段发生了什么变化、为何推动下一段。"
                    "五段必须是同一人物、同一时间和同一空间中的连续小故事。开头用异常、选择或未完成动作制造好奇，不使用空泛提问和广告口号；"
                    "痛点用人物行为表现，不直接宣讲；产品只能在冲突建立后自然出现；结尾给低压力行动号召。旁白应口语、克制、可朗读，删掉可套用到其他产品的句子。"
                    "第 3 段只展示获批奶液来源倒入恒温杯；第 4 段只展示恒温杯经圆形出液口倒入独立干净奶瓶，不得在同一段合并两个方向。"
                    "便携恒温杯与奶瓶是两个独立物体。不得虚构功能、品牌、医疗效果或保证性声明。"
                    f"获批产品事实与硬约束：{product_facts or '未提供'}。"
                    f"必须修复的上轮反馈：{rewrite_reason or '无'}。"
                    f"获批内容策略：{strategy_brief}。素材分析：{analysis_report}。"
                    "交付前静默检查：是否有具体生活细节、五段因果是否连续、人物说话是否自然、产品动作是否准确；不满足时先重写再返回 JSON。"
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
        ("钩子", "0-6s", "夜间准备，不必占满你的休息时间。"),
        ("痛点", "6-12s", "奶液变冷和等待，会让夜间准备更困难。"),
        ("方案", "12-18s", "将允许的奶液来源倒入恒温杯。"),
        ("证明", "18-24s", "准备完成后，经圆形出液口倒入独立的干净奶瓶。"),
        ("行动号召", "24-30s", "收藏这套更从容的夜间准备方法。"),
    ]
    raw = value if isinstance(value, list) else []
    sections: list[dict[str, Any]] = []
    for index, (role, timing, voiceover) in enumerate(defaults, start=1):
        item = raw[index - 1] if index - 1 < len(raw) and isinstance(raw[index - 1], dict) else {}
        chinese_line = _clean_voiceover(str(item.get("voiceover_zh") or item.get("voiceover_en") or voiceover))
        sections.append(
            {
                "number": index,
                "role": role,
                "timing": timing,
                "voiceover_zh": chinese_line or _default_chinese_voiceover(index),
                "scene_zh": str(item.get("scene_zh") or _default_scene(index)),
                "action_zh": _default_action(index) if index in {3, 4} else str(item.get("action_zh") or _default_action(index)),
                "story_beat_zh": str(item.get("story_beat_zh") or _default_story_beat(index)),
                "subtitle_zh": chinese_line or _default_chinese_voiceover(index),
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

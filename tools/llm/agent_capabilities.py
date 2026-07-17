from __future__ import annotations

import json
from typing import Any

from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


def _chat(context: ToolContext, system: str, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    require_env(context, "DOUBAO_API_KEY")
    return ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    )


@register_tool("competitor_research")
def competitor_research(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload["project_id"])
    source = str(payload.get("source_text") or "No transcript supplied; use available structural metadata only.")
    if context.mock:
        body = {
            "viral_patterns": ["痛点前置钩子", "六秒一拍的节奏", "产品可见的真实演示"],
            "audience_insights": ["夜间照护者看重快速、清晰和低负担的准备流程"],
            "pacing_notes": ["0-6s 钩子", "6-12s 痛点", "12-18s 方案", "18-24s 证明", "24-30s 行动号召"],
            "content_risks": ["不得复制竞品文案、品牌、声明或产品外观。"],
            "source_summary": source[:500],
        }
        meta = {"model": "mock"}
    else:
        body, meta = _chat(
            context,
            "你是短视频研究智能体，只提炼可复用的结构与节奏，必须返回严格 JSON，绝不复制竞品文案、品牌或声明。所有文本字段一律使用简体中文。",
            "请返回 viral_patterns、audience_insights、pacing_notes、content_risks、source_summary 五个字段，全部使用简体中文。素材：\n" + source[:5000],
        )
    artifact = {
        "version": "1.0",
        "project_id": project_id,
        "source_refs": [str(item) for item in payload.get("source_refs") or []],
        "viral_patterns": _list(body.get("viral_patterns")),
        "audience_insights": _list(body.get("audience_insights")),
        "pacing_notes": _list(body.get("pacing_notes")),
        "content_risks": _list(body.get("content_risks")),
        "source_summary": str(body.get("source_summary") or source[:500]),
    }
    return ToolResult.success({"research_brief": artifact}, meta={"tool": "competitor_research", **meta})


@register_tool("content_strategy")
def content_strategy(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload["project_id"])
    research = payload.get("research_brief") or {}
    guardrails_obj = _guardrail_object(payload.get("product_guardrails"))
    guardrails_text = json.dumps(guardrails_obj, ensure_ascii=False, sort_keys=True) if guardrails_obj else ""
    if context.mock:
        body = {
            "content_direction": "以夜间照护者的平静叙事，从困扰过渡到安全、正确的产品演示。",
            "target_audience": ["在夜间或出行时准备喂养的照护者"],
            "selling_point_priority": ["便携机身", "简单准备", "床头与出行场景"],
            "hook_options": ["别让夜间冲奶占据你的整晚。"],
            "cta_options": ["收藏这条，让家里或出行时的喂养更从容。"],
            "forbidden_claims": ["医疗效果", "保证性能", "竞品对比", "98°C"],
        }
        meta = {"model": "mock"}
    else:
        body, meta = _chat(
            context,
            "你是注重品牌安全的内容策略智能体，必须基于已批准的产品事实返回严格 JSON。所有文本字段一律使用简体中文。",
            f"研究简报：{research}\n产品安全边界：{guardrails_text}\n请返回 content_direction、target_audience、selling_point_priority、hook_options、cta_options、forbidden_claims，全部使用简体中文。",
        )
    artifact = {
        "version": "1.0",
        "project_id": project_id,
        "content_direction": str(body.get("content_direction") or "产品安全的照护者故事。"),
        "target_audience": _list(body.get("target_audience")),
        "selling_point_priority": _list(body.get("selling_point_priority")),
        "hook_options": _list(body.get("hook_options")),
        "cta_options": _list(body.get("cta_options")),
        "forbidden_claims": _list(body.get("forbidden_claims")),
        "product_guardrails": guardrails_obj,
    }
    return ToolResult.success({"strategy_brief": artifact}, meta={"tool": "content_strategy", **meta})


@register_tool("script_breakdown")
def script_breakdown(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload["project_id"])
    script = payload.get("script_copy") or {}
    beats = []
    for section in script.get("sections") or []:
        beats.append(
            {
                "number": int(section.get("number") or len(beats) + 1),
                "timing": str(section.get("timing") or ""),
                "role": str(section.get("role") or ""),
                "voiceover": str(section.get("voiceover_en") or ""),
                "intent": _intent(str(section.get("role") or "")),
                "visual_requirement": " ".join(
                    value for value in (
                        str(section.get("scene_zh") or ""),
                        str(section.get("action_zh") or ""),
                        str(section.get("story_beat_zh") or ""),
                        "使用已批准产品素材，并保持人物、场景与产品连续性。",
                    ) if value
                ),
                "human_editable": True,
            }
        )
    artifact = {
        "version": "1.0",
        "project_id": project_id,
        "total_duration_s": float(script.get("total_duration_s") or 0),
        "beats": beats,
        "continuity_requirements": [
            "One consistent caregiver identity across all person-visible shots.",
            "The product must match the approved white-background identity image.",
            "If visible, the display must read 98°F and never 98°C.",
        ],
    }
    return ToolResult.success({"script_breakdown": artifact}, meta={"tool": "script_breakdown", "model": "deterministic"})


def _list(value: Any) -> list[str]:
    return [str(item).strip() for item in value or [] if str(item).strip()]


def _guardrail_object(value: Any) -> dict[str, Any]:
    """Normalize product guardrails to a nested object.

    Upstream passes guardrails as a JSON string (product_guardrail_text). Persist
    them as a structured object so downstream consumers never have to double-parse.
    """
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _intent(role: str) -> str:
    intents = {"钩子": "在前三秒建立注意力", "痛点": "让用户识别真实困扰", "方案": "展示正确且安全的解决方式", "证明": "用可感知细节说明价值", "行动号召": "给出低压力的下一步行动"}
    return intents.get(role, "推动故事自然向前")

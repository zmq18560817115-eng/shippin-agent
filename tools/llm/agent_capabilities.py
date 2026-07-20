from __future__ import annotations

import json
from typing import Any

from libshared.agent_contracts import agent_system_prompt
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


def _chat(context: ToolContext, agent_id: str, system: str, prompt: str) -> tuple[dict[str, Any], dict[str, Any]]:
    require_env(context, "DOUBAO_API_KEY")
    return ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[{"role": "system", "content": agent_system_prompt(agent_id) + system}, {"role": "user", "content": prompt}],
    )


@register_tool("competitor_research")
def competitor_research(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload["project_id"])
    source = str(payload.get("source_text") or "未提供转写文本，仅依据现有结构化元数据进行研究。")
    if context.mock:
        body = {
            "viral_patterns": ["先呈现问题再给出方案", "每六秒推进一个叙事节拍", "用可见动作展示产品"],
            "audience_insights": ["夜间照护者重视准备速度、信息清晰和低操作负担"],
            "pacing_notes": ["0-6秒：钩子", "6-12秒：痛点", "12-18秒：方案", "18-24秒：证明", "24-30秒：行动号召"],
            "content_risks": ["不得复制竞品文案、品牌、宣称或产品外观。"],
            "source_summary": source[:500],
        }
        meta = {"model": "mock"}
    else:
        body, meta = _chat(
            context,
            "research",
            "你是短视频研究 Agent。只提取可复用的内容结构，不复制竞品文案或宣称。严格返回 JSON，所有字段值必须使用简体中文。",
            "返回 viral_patterns、audience_insights、pacing_notes、content_risks、source_summary。节奏统一为五个六秒段。素材：\n" + source[:5000],
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
    guardrails = _object(payload.get("product_guardrails"))
    if context.mock:
        body = {
            "content_direction": "用平静的夜间照护故事，从准备不便自然推进到安全、清晰的产品使用展示。",
            "target_audience": ["需要在夜间或出行时准备喂养用品的照护者"],
            "selling_point_priority": ["便携机身", "准备步骤清晰", "适合床头与出行场景"],
            "hook_options": ["夜间准备，不必占满你的休息时间。"],
            "cta_options": ["收藏这套更从容的夜间准备方法。"],
            "forbidden_claims": ["医疗效果", "保证性性能宣称", "贬低竞品", "98°C"],
        }
        meta = {"model": "mock"}
    else:
        body, meta = _chat(
            context,
            "strategy",
            "你是品牌安全内容策略 Agent。必须以获批产品事实为依据，严格返回 JSON，所有字段值使用简体中文。",
            "研究结论：" + json.dumps(research, ensure_ascii=False) + "\n产品安全规则：" + json.dumps(guardrails, ensure_ascii=False)
            + "\n返回 content_direction、target_audience、selling_point_priority、hook_options、cta_options、forbidden_claims。",
        )
    artifact = {
        "version": "1.0",
        "project_id": project_id,
        "content_direction": str(body.get("content_direction") or "符合产品安全规则的照护者故事。"),
        "target_audience": _list(body.get("target_audience")),
        "selling_point_priority": _list(body.get("selling_point_priority")),
        "hook_options": _list(body.get("hook_options")),
        "cta_options": _list(body.get("cta_options")),
        "forbidden_claims": _list(body.get("forbidden_claims")),
        "product_guardrails": guardrails,
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
                "voiceover": str(section.get("voiceover_zh") or section.get("voiceover_en") or ""),
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
            "所有出现人物的镜头必须保持同一位照护者身份。",
            "产品外观必须与获批白底身份图一致。",
            "温度可见时必须显示 98°F，禁止显示 98°C。",
        ],
    }
    return ToolResult.success({"script_breakdown": artifact}, meta={"tool": "script_breakdown", "model": "deterministic"})


def _list(value: Any) -> list[str]:
    return [str(item).strip() for item in value or [] if str(item).strip()]


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {"说明": value.strip()}
        return parsed if isinstance(parsed, dict) else {"说明": parsed}
    return {}


def _intent(role: str) -> str:
    intents = {"钩子": "在前三秒建立注意力", "痛点": "让用户识别真实困扰", "方案": "展示正确且安全的解决方式", "证明": "用可感知细节说明价值", "行动号召": "给出低压力的下一步行动"}
    return intents.get(role, "推动故事自然向前")

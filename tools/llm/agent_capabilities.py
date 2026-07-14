from __future__ import annotations

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
            "viral_patterns": ["problem-first hook", "six-second beats", "visible product demonstration"],
            "audience_insights": ["late-night caregivers value speed, clarity, and low-friction preparation"],
            "pacing_notes": ["0-3s hook", "3-12s pain", "12-24s solution and proof", "24-30s CTA"],
            "content_risks": ["Do not copy competitor wording, branding, claims, or product appearance."],
            "source_summary": source[:500],
        }
        meta = {"model": "mock"}
    else:
        body, meta = _chat(
            context,
            "You are a short-video research agent. Extract reusable structure only. Return strict JSON and never copy competitor wording or claims.",
            "Return viral_patterns, audience_insights, pacing_notes, content_risks, and source_summary. Source:\n" + source[:5000],
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
    guardrails = str(payload.get("product_guardrails") or "")
    if context.mock:
        body = {
            "content_direction": "A calm late-night caregiver story that moves from friction to safe product demonstration.",
            "target_audience": ["caregivers preparing feeds at night or while traveling"],
            "selling_point_priority": ["portable form", "simple preparation", "nightstand and travel use"],
            "hook_options": ["Bottle prep should not take over your night."],
            "cta_options": ["Save this for calmer feeds at home or on the go."],
            "forbidden_claims": ["medical outcomes", "guaranteed performance", "competitor comparisons", "98°C"],
        }
        meta = {"model": "mock"}
    else:
        body, meta = _chat(
            context,
            "You are a brand-safe content strategy agent. Return strict JSON grounded in approved product facts.",
            f"Research: {research}\nProduct guardrails: {guardrails}\nReturn content_direction, target_audience, selling_point_priority, hook_options, cta_options, forbidden_claims.",
        )
    artifact = {
        "version": "1.0",
        "project_id": project_id,
        "content_direction": str(body.get("content_direction") or "Product-safe caregiver story."),
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
                "voiceover": str(section.get("voiceover_en") or ""),
                "intent": _intent(str(section.get("role") or "")),
                "visual_requirement": "Use approved product assets and preserve product, scene, and character continuity.",
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


def _intent(role: str) -> str:
    intents = {"钩子": "stop the scroll", "痛点": "make the audience recognize the situation", "方案": "show the safe solution", "证明": "demonstrate a grounded benefit", "行动号召": "prompt a low-pressure next action"}
    return intents.get(role, "advance the story")

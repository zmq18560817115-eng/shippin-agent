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
    rewrite_reason = str(payload.get("rewrite_reason") or "").strip()
    product_facts = product_library.product_guardrail_text(product_id)
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You write brand-safe English TikTok scripts for baby product overseas localization. "
                    "Return strict JSON only. Avoid medical, guarantee, best, pain-free, and competitor claims."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create script_copy JSON for product_id "
                    f"{product_id}. Use exactly 5 sections with roles 钩子, 痛点, 方案, 证明, 行动号召 and continuous timings "
                    "0-6s, 6-12s, 12-18s, 18-24s, 24-30s. Product fact: portable warming cup is separate from baby bottle; "
                    "milk is poured into the cup, warmed/kept warm, then poured through the spout into a clean bottle. "
                    f"Approved product facts and hard constraints: {product_facts or 'not provided'}. "
                    f"Previous review feedback that must be fixed: {rewrite_reason or 'none'}. "
                    f"Analysis: {analysis_report}"
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
        ("方案", "12-18s", "Pour milk into the warming cup and prepare a clean bottle when it is ready."),
        ("证明", "18-24s", "Its portable shape fits a nightstand or travel bag."),
        ("行动号召", "24-30s", "Save this for calmer feeds at home or on the go."),
    ]
    raw = value if isinstance(value, list) else []
    sections: list[dict[str, Any]] = []
    for index, (role, timing, voiceover) in enumerate(defaults, start=1):
        item = raw[index - 1] if index - 1 < len(raw) and isinstance(raw[index - 1], dict) else {}
        line = _clean_voiceover(str(item.get("voiceover_en") or item.get("subtitle_en") or voiceover))
        sections.append(
            {
                "number": index,
                "role": role,
                "timing": timing,
                "voiceover_en": line,
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


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return fallback

from __future__ import annotations

from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


@register_tool("doubao_analyze")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
        return _execute_real(payload, context)
    project_id = str(payload.get("project_id") or "ref-mock")
    transcript = str(payload.get("transcript_text") or "")
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "material_meta_ref": str(payload.get("source_material_id") or payload.get("source_url") or ""),
        "hook_3s": "Night feeds should feel easier.",
        "structure": ["钩子", "痛点", "方案", "证明", "行动号召"],
        "voiceover_text": transcript or "Mock transcript for portable warming cup.",
        "pacing": [
            {"start_s": 0, "end_s": 6, "role": "钩子"},
            {"start_s": 6, "end_s": 12, "role": "痛点"},
            {"start_s": 12, "end_s": 18, "role": "方案"},
            {"start_s": 18, "end_s": 24, "role": "证明"},
            {"start_s": 24, "end_s": 30, "role": "行动号召"},
        ],
        "keyframes": [],
        "fingerprint": "mock-analysis",
    }
    artifacts.validate_artifact("analysis_report", report)
    return ToolResult.success(
        {"analysis_report": report},
        cost_cny=context.pricing_for("doubao_analyze") if not context.mock else 0.0,
        meta={"tool": "doubao_analyze", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    transcript = str(payload.get("transcript_text") or payload.get("source_url") or "Manual competitor link intake.")
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze short-video structure for brand-safe overseas localization. "
                    "Return strict JSON only. Do not copy competitor wording or unsupported claims."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create an analysis_report JSON object with fields: hook_3s, structure, "
                    "voiceover_text, pacing, keyframes, fingerprint for a 30-second video. Product: portable warming cup. "
                    "Use only generic structure insights from the source. Source text/link: "
                    f"{transcript[:1500]}"
                ),
            },
        ],
    )
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "material_meta_ref": str(payload.get("source_material_id") or payload.get("source_url") or ""),
        "hook_3s": _string(response.get("hook_3s"), "Bottle prep without the long wait."),
        "structure": _string_list(response.get("structure"), ["钩子", "痛点", "方案", "行动号召"]),
        "voiceover_text": _string(response.get("voiceover_text"), transcript),
        "pacing": _normalize_pacing(response.get("pacing")),
        "keyframes": _string_list(response.get("keyframes"), []),
        "fingerprint": _string(response.get("fingerprint"), f"ark-{meta.get('response_id') or 'analysis'}"),
    }
    artifacts.validate_artifact("analysis_report", report)
    return ToolResult.success(
        {"analysis_report": report},
        cost_cny=context.pricing_for("doubao_analyze"),
        meta={"tool": "doubao_analyze", "mock": False, **meta},
    )


def _normalize_pacing(value: Any) -> list[dict[str, Any]]:
    roles = ["钩子", "痛点", "方案", "证明", "行动号召"]
    if isinstance(value, list):
        result = []
        for index, item in enumerate(value[:6]):
            if not isinstance(item, dict):
                continue
            start = _number(item.get("start_s"), index * 6)
            end = _number(item.get("end_s"), start + 6)
            if end <= start:
                end = start + 6
            result.append(
                {
                    "start_s": start,
                    "end_s": end,
                    "role": _string(item.get("role"), roles[min(index, len(roles) - 1)]),
                    "note": _string(item.get("note"), ""),
                }
            )
        if result:
            return result
    return [
        {"start_s": 0, "end_s": 6, "role": "钩子"},
        {"start_s": 6, "end_s": 12, "role": "痛点"},
        {"start_s": 12, "end_s": 18, "role": "方案"},
        {"start_s": 18, "end_s": 24, "role": "证明"},
        {"start_s": 24, "end_s": 30, "role": "行动号召"},
    ]


def _string(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _string_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return fallback


def _number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)

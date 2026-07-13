from __future__ import annotations

from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.tool_registry import register_tool


@register_tool("doubao_analyze")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
    project_id = str(payload.get("project_id") or "ref-mock")
    transcript = str(payload.get("transcript_text") or "")
    report = {
        "version": "2.0",
        "project_id": project_id,
        "source_link_id": payload.get("source_link_id"),
        "hook_3s": "Night feeds should feel easier.",
        "structure": ["钩子", "痛点", "方案", "证明", "行动号召"],
        "voiceover_text": transcript or "Mock transcript for portable warming cup.",
        "pacing": [
            {"start_s": 0, "end_s": 3, "role": "钩子"},
            {"start_s": 3, "end_s": 6, "role": "痛点"},
            {"start_s": 6, "end_s": 9, "role": "方案"},
            {"start_s": 9, "end_s": 12, "role": "证明"},
            {"start_s": 12, "end_s": 15, "role": "行动号召"},
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

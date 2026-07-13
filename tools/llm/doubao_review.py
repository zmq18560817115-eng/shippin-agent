from __future__ import annotations

from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.tool_registry import register_tool


@register_tool("doubao_review")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
    project_id = str(payload.get("project_id") or "ref-mock")
    report = {
        "version": "2.0",
        "project_id": project_id,
        "artifact_type": "review_report",
        "status": "PASS",
        "scores": {
            "hook": 8,
            "clarity": 8,
            "compliance": 10,
            "product_fit": 9,
            "pacing": 8,
            "cta": 8,
            "asset_traceability": 9,
        },
        "comments": ["Mock review passed with product-safe wording."],
    }
    artifacts.validate_artifact("review_report", report)
    return ToolResult.success(
        {"review_report": report},
        cost_cny=context.pricing_for("doubao_review") if not context.mock else 0.0,
        meta={"tool": "doubao_review", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )

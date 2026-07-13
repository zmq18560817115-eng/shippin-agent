from __future__ import annotations

from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.llm.mock_artifacts import mock_script_copy
from tools.tool_registry import register_tool


@register_tool("doubao_script")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
    project_id = str(payload.get("project_id") or "ref-mock")
    product_id = str(payload.get("product_id") or "便携恒温杯")
    script_copy = mock_script_copy(project_id, product_id, provider="doubao")
    artifacts.validate_artifact("script_copy", script_copy)
    return ToolResult.success(
        {"script_copy": script_copy},
        cost_cny=context.pricing_for("doubao_script") if not context.mock else 0.0,
        meta={"tool": "doubao_script", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )

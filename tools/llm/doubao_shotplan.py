from __future__ import annotations

from typing import Any

from libshared import artifacts
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.llm.mock_artifacts import mock_script_copy, mock_shot_plan
from tools.tool_registry import register_tool


@register_tool("doubao_shotplan")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
    project_id = str(payload.get("project_id") or "ref-mock")
    script_copy = payload.get("script_copy") or mock_script_copy(project_id)
    shot_plan = mock_shot_plan(project_id, script_copy)
    artifacts.validate_artifact("shot_plan", shot_plan, script_copy=script_copy)
    return ToolResult.success(
        {"shot_plan": shot_plan},
        cost_cny=context.pricing_for("doubao_shotplan") if not context.mock else 0.0,
        meta={"tool": "doubao_shotplan", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )

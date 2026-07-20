from __future__ import annotations

from typing import Any

from libshared import artifacts
from libshared.agent_contracts import agent_system_prompt
from tools.base_tool import ToolContext, ToolResult, require_env
from tools.providers import ark
from tools.tool_registry import register_tool


@register_tool("doubao_review")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "DOUBAO_API_KEY")
        return _execute_real(payload, context)
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
        "comments": ["演练审核通过：文案符合当前产品安全表达规则。"],
    }
    artifacts.validate_artifact("review_report", report)
    return ToolResult.success(
        {"review_report": report},
        cost_cny=context.pricing_for("doubao_review") if not context.mock else 0.0,
        meta={"tool": "doubao_review", "mock": context.mock, "model": "mock" if context.mock else "doubao"},
    )


def _execute_real(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-real")
    script_copy = payload.get("script_copy") or {}
    analysis_report = payload.get("analysis_report") or {}
    response, meta = ark.chat_json(
        context,
        api_key_names=("DOUBAO_API_KEY", "ARK_DOUBAO_API_KEY", "ARK_API_KEY"),
        messages=[
            {
                "role": "system",
                "content": (
                    agent_system_prompt("review")
                    + "You review baby product short-video scripts for compliance and product factuality. "
                    "Return strict JSON only with status PASS, WARNING, or BLOCKED."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review this script. Block unsupported medical, guarantee, best, pain-free, lactation, "
                    "competitor, or unsafe baby-product claims. Return status, scores, comments. "
                    f"Analysis: {analysis_report} Script: {script_copy}"
                ),
            },
        ],
        temperature=0.1,
    )
    status = str(response.get("status") or "PASS").upper()
    if status not in {"PASS", "WARNING", "BLOCKED"}:
        status = "WARNING"
    report = {
        "version": "2.0",
        "project_id": project_id,
        "artifact_type": "review_report",
        "status": status,
        "scores": response.get("scores") if isinstance(response.get("scores"), dict) else {},
        "comments": _comments(response.get("comments")),
    }
    artifacts.validate_artifact("review_report", report)
    return ToolResult.success(
        {"review_report": report},
        cost_cny=context.pricing_for("doubao_review"),
        meta={"tool": "doubao_review", "mock": False, **meta},
    )


def _comments(value: Any) -> list[str]:
    if isinstance(value, list):
        comments = [str(item).strip() for item in value if str(item).strip()]
        if comments:
            return comments
    if value:
        return [str(value).strip()]
    return ["豆包审核已完成。"]

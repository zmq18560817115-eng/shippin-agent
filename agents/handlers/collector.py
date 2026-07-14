from __future__ import annotations

from typing import Any, Mapping

from agents.base import FatalTaskError, ValidationTaskError, register_handler
from tools import tool_registry


@register_handler("collector")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(task.get("payload_json") or {})
    task_type = str(task.get("task_type") or "manual_import")
    if task_type not in {"manual_import", "tiktok_oembed", "default"}:
        raise ValidationTaskError(f"collector task_type is not supported: {task_type}")
    tool_name = "tiktok_oembed" if task_type == "tiktok_oembed" else "manual_import"
    result = tool_registry.execute_tool(
        tool_name,
        payload,
        context={"mock": bool(payload.get("mock", True))},
    )
    if not result.ok:
        error = result.error or {"message": f"{tool_name} failed"}
        category = str(error.get("category") or "tool_error")
        message = str(error.get("message") or error)
        if category == "validation":
            raise ValidationTaskError(message)
        raise FatalTaskError(message)
    return result.data

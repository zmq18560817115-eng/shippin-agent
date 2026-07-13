from __future__ import annotations

from typing import Any, Mapping

from agents.base import FatalTaskError, ValidationTaskError, register_handler
from tools import tool_registry


@register_handler("collector")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(task.get("payload_json") or {})
    task_type = str(task.get("task_type") or "manual_import")
    if task_type not in {"manual_import", "default"}:
        raise ValidationTaskError(f"collector task_type is not supported: {task_type}")
    result = tool_registry.execute_tool(
        "manual_import",
        payload,
        context={"mock": bool(payload.get("mock", True))},
    )
    if not result.ok:
        error = result.error or {"message": "manual_import failed"}
        category = str(error.get("category") or "tool_error")
        message = str(error.get("message") or error)
        if category == "validation":
            raise ValidationTaskError(message)
        raise FatalTaskError(message)
    return result.data

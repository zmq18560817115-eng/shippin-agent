from __future__ import annotations

from typing import Any, Mapping

from agents.base import BlockedTaskError, register_handler


@register_handler("analysis")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    raise BlockedTaskError("analysis handler is implemented with the engine and tools")

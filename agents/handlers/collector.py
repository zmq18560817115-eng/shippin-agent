from __future__ import annotations

from typing import Any, Mapping

from agents.base import BlockedTaskError, register_handler


@register_handler("collector")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    raise BlockedTaskError("collector handler is implemented in block 7")

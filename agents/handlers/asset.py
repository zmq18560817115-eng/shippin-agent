from __future__ import annotations

from typing import Any, Mapping

from agents.base import BlockedTaskError, register_handler


@register_handler("asset")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    raise BlockedTaskError("asset handler is implemented with white-background product checks")

from __future__ import annotations

from typing import Any, Mapping

from agents.base import BlockedTaskError, register_handler


@register_handler("media")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    raise BlockedTaskError("media handler is implemented with shot_gen and compose task types")

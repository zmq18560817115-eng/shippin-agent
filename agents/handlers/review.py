from __future__ import annotations

from typing import Any, Mapping

from agents.base import BlockedTaskError, register_handler


@register_handler("review")
def handle_task(task: Mapping[str, Any]) -> dict[str, Any]:
    raise BlockedTaskError("review handler is implemented with script_review, final_qa, and archive")

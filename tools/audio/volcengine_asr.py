from __future__ import annotations

from typing import Any

from tools.base_tool import ToolContext, ToolResult, require_env
from tools.tool_registry import register_tool


@register_tool("volcengine_asr")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    if not context.mock:
        require_env(context, "VOLCENGINE_ASR_APP_KEY")
    transcript = payload.get("transcript_text") or (
        "Night feeds should feel easier. Cold milk and long waits make bedtime harder. "
        "Pour milk into the warming cup and prep the bottle."
    )
    return ToolResult.success(
        {
            "transcript_text": transcript,
            "segments": [
                {"start_s": 0, "end_s": 5, "text": transcript},
            ],
        },
        meta={"tool": "volcengine_asr", "mock": context.mock, "audio_path": payload.get("audio_path")},
    )

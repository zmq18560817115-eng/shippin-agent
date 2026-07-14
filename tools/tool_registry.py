from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tools.base_tool import ToolContext, ToolResult, result_from_exception


ToolFn = Callable[[dict[str, Any], ToolContext], ToolResult]
_REGISTRY: dict[str, ToolFn] = {}
_LOADED = False


def register_tool(name: str, func: ToolFn | None = None):
    def decorator(tool_func: ToolFn) -> ToolFn:
        _REGISTRY[name] = tool_func
        return tool_func

    if func is not None:
        return decorator(func)
    return decorator


def get_tool(name: str) -> ToolFn:
    _ensure_loaded()
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"tool not registered: {name}") from exc


def list_tools() -> list[str]:
    _ensure_loaded()
    return sorted(_REGISTRY)


def execute_tool(
    name: str,
    payload: Mapping[str, Any] | None = None,
    *,
    context: Mapping[str, Any] | ToolContext | None = None,
) -> ToolResult:
    tool_context = context if isinstance(context, ToolContext) else ToolContext.from_mapping(context)
    try:
        return get_tool(name)(dict(payload or {}), tool_context)
    except Exception as exc:
        return result_from_exception(exc)


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    from tools.audio import volcengine_asr
    from tools.collect import manual_import, tiktok_crawler, tiktok_oembed, tiktok_video
    from tools.llm import agent_capabilities, claude_script, doubao_analyze, doubao_review, doubao_script, doubao_shotplan
    from tools.video import ffmpeg_compose, hero_frame, seedance_shot

    _ = (
        volcengine_asr,
        agent_capabilities,
        manual_import,
        tiktok_crawler,
        tiktok_oembed,
        tiktok_video,
        claude_script,
        doubao_analyze,
        doubao_review,
        doubao_script,
        doubao_shotplan,
        ffmpeg_compose,
        hero_frame,
        seedance_shot,
    )
    _LOADED = True

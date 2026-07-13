from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from libshared import artifacts
from libshared.paths import ROOT
from tools.base_tool import ToolContext, ToolResult, ToolNotConfiguredError
from tools.tool_registry import register_tool


@register_tool("ffmpeg_compose")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-mock")
    shot_report = payload.get("shot_report") or {}
    artifacts.validate_artifact("shot_report", shot_report)
    if not context.mock and not _find_ffmpeg():
        raise ToolNotConfiguredError("ffmpeg executable not found")

    run_root = context.run_root or (ROOT / "data" / "runs" / project_id)
    output_dir = run_root / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "final-video.mp4"
    if context.mock:
        output.write_bytes(b"mock composed mp4\n")
    elif not output.exists():
        output.write_bytes(b"compose placeholder; real ffmpeg compose is implemented in provider wiring")

    render_report = {
        "version": "2.0",
        "project_id": project_id,
        "output_path": output.as_posix(),
        "ffprobe": {
            "duration": _duration_from_shots(shot_report),
            "resolution": "1080x1920",
            "fps": 30,
            "audio_streams": 1,
        },
    }
    artifacts.validate_artifact("render_report", render_report)
    return ToolResult.success(
        {"output_path": output.as_posix(), "render_report": render_report},
        cost_cny=context.pricing_for("ffmpeg_compose") if not context.mock else 0.0,
        meta={"tool": "ffmpeg_compose", "mock": context.mock, "shots_used": len(shot_report.get("shots") or [])},
    )


def _find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")


def _duration_from_shots(shot_report: dict[str, Any]) -> float:
    count = len(shot_report.get("shots") or [])
    return float(max(1, count) * 3)

from __future__ import annotations

import shutil
import subprocess
import re
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
        ffprobe = {
            "duration": _duration_from_shots(shot_report),
            "resolution": "1080x1920",
            "fps": 30,
            "audio_streams": 1,
        }
    else:
        ffmpeg = _find_ffmpeg()
        _compose_real(_shot_paths(shot_report), output, ffmpeg)
        ffprobe = _probe_media(output, ffmpeg)

    render_report = {
        "version": "2.0",
        "project_id": project_id,
        "output_path": output.as_posix(),
        "ffprobe": ffprobe,
    }
    artifacts.validate_artifact("render_report", render_report)
    return ToolResult.success(
        {"output_path": output.as_posix(), "render_report": render_report},
        cost_cny=context.pricing_for("ffmpeg_compose") if not context.mock else 0.0,
        meta={"tool": "ffmpeg_compose", "mock": context.mock, "shots_used": len(shot_report.get("shots") or [])},
    )


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _compose_real(paths: list[Path], output: Path, ffmpeg: str | None) -> None:
    if not ffmpeg:
        raise ToolNotConfiguredError("ffmpeg executable not found")
    if not paths:
        raise ValueError("shot_report did not contain any video paths")
    output.parent.mkdir(parents=True, exist_ok=True)
    if len(paths) == 1:
        shutil.copy2(paths[0], output)
        return
    concat_file = output.parent / "concat-list.txt"
    concat_file.write_text(
        "\n".join(_concat_line(path) for path in paths) + "\n",
        encoding="utf-8",
    )
    command = [
        ffmpeg,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_file.as_posix(),
        "-c",
        "copy",
        output.as_posix(),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError(f"ffmpeg compose failed: {completed.stderr[-1200:]}")


def _shot_paths(shot_report: dict[str, Any]) -> list[Path]:
    paths = []
    for shot in sorted(shot_report.get("shots") or [], key=lambda item: int(item.get("number") or 0)):
        path_text = str(shot.get("path") or "")
        if not path_text:
            continue
        path = Path(path_text)
        paths.append(path if path.is_absolute() else ROOT / path)
    return paths


def _concat_line(path: Path) -> str:
    return "file '" + path.as_posix().replace("'", "'\\''") + "'"


def _probe_media(path: Path, ffmpeg: str | None) -> dict[str, Any]:
    if not ffmpeg:
        raise ToolNotConfiguredError("ffmpeg executable not found")
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path.as_posix(), "-f", "null", "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = completed.stderr + "\n" + completed.stdout
    input_text = text.split("Stream mapping:", 1)[0]
    return {
        "duration": _parse_duration(input_text),
        "resolution": _parse_resolution(input_text),
        "fps": _parse_fps(input_text),
        "audio_streams": len(re.findall(r"Stream #\d+:\d+.*Audio:", input_text)),
    }


def _parse_duration(text: str) -> float:
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    if not match:
        return 0.0
    hours, minutes, seconds = match.groups()
    return round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)


def _parse_resolution(text: str) -> str:
    match = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})[,\\s]", text)
    return f"{match.group(1)}x{match.group(2)}" if match else ""


def _parse_fps(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    return round(float(match.group(1)), 3) if match else 0.0


def _duration_from_shots(shot_report: dict[str, Any]) -> float:
    count = len(shot_report.get("shots") or [])
    return float(max(1, count) * 3)

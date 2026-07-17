from __future__ import annotations

import shutil
import subprocess
import re
import tempfile
import os
from pathlib import Path
from typing import Any

from libshared import artifacts
from libshared.paths import ROOT
from tools.base_tool import ToolContext, ToolResult, ToolNotConfiguredError
from tools.tool_registry import register_tool

DELIVERY_WIDTH = 720
DELIVERY_HEIGHT = 1280


@register_tool("ffmpeg_compose")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    project_id = str(payload.get("project_id") or "ref-mock")
    shot_report = payload.get("shot_report") or {}
    artifacts.validate_artifact("shot_report", shot_report)
    if not context.mock and not _find_ffmpeg():
        raise ToolNotConfiguredError("ffmpeg executable not found")

    run_root = (context.run_root or (ROOT / "data" / "runs" / project_id)).resolve()
    output_dir = run_root / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "final-video.mp4"
    if context.mock:
        write_mock_video(output, _duration_from_shots(shot_report))
        ffprobe = {
            "duration": _duration_from_shots(shot_report),
            "resolution": "720x1280",
            "fps": 30,
            "audio_streams": 1,
        }
        input_probes = [
            {
                **ffprobe,
                "duration": float(shot.get("duration_sec") or 6),
            }
            for shot in shot_report.get("shots") or []
        ]
    else:
        ffmpeg = _find_ffmpeg()
        shot_paths = _shot_paths(shot_report)
        input_probes = [_probe_media(path, ffmpeg) for path in shot_paths]
        _compose_real(shot_paths, output, ffmpeg, shot_report)
        ffprobe = _probe_media(output, ffmpeg)
        if ffprobe.get("resolution") != f"{DELIVERY_WIDTH}x{DELIVERY_HEIGHT}":
            raise RuntimeError("final video must be exactly 720x1280")

    review_frame_dir = output_dir / "review_frames"
    review_frames = _extract_review_frames(output, review_frame_dir, _find_ffmpeg()) if output.is_file() else []

    render_report = {
        "version": "2.0",
        "project_id": project_id,
        "output_path": output.as_posix(),
        "ffprobe": ffprobe,
        "input_probes": input_probes,
        "review_frame_paths": [path.as_posix() for path in review_frames],
    }
    artifacts.validate_artifact("render_report", render_report)
    return ToolResult.success(
        {"output_path": output.as_posix(), "render_report": render_report},
        cost_cny=context.pricing_for("ffmpeg_compose") if not context.mock else 0.0,
        meta={"tool": "ffmpeg_compose", "mock": context.mock, "shots_used": len(shot_report.get("shots") or [])},
    )


def write_mock_video(output: Path, duration_sec: float) -> None:
    """Produce a structurally playable mock delivery so final QA remains strict."""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        raise ToolNotConfiguredError("ffmpeg executable not found for mock delivery")
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(tempfile.gettempdir()) / f"vaf-mock-720x1280-{max(1, int(round(duration_sec)))}s.mp4"
    if cache.is_file() and cache.stat().st_size > 10_000:
        shutil.copy2(cache, output)
        return
    target = cache.with_suffix(f".{os.getpid()}.tmp.mp4")
    command = [
        ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x182033:s=720x1280:r=30",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", str(max(1, duration_sec)),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-movflags", "+faststart", "-shortest", target.as_posix(),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not target.is_file():
        raise RuntimeError(f"mock compose failed: {completed.stderr[-1200:]}")
    target.replace(cache)
    shutil.copy2(cache, output)


def _find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _compose_real(paths: list[Path], output: Path, ffmpeg: str | None, shot_report: dict[str, Any]) -> None:
    if not ffmpeg:
        raise ToolNotConfiguredError("ffmpeg executable not found")
    if not paths:
        raise ValueError("shot_report did not contain any video paths")
    output.parent.mkdir(parents=True, exist_ok=True)
    normalized_dir = output.parent / "normalized-shots"
    normalized_dir.mkdir(parents=True, exist_ok=True)
    normalized = [
        _normalize_shot(path, normalized_dir / f"shot-{index:03d}.mp4", ffmpeg, float((shot_report.get("shots") or [])[index - 1].get("duration_sec") or 6))
        for index, path in enumerate(paths, start=1)
    ]
    concat_file = output.parent / "concat-list.txt"
    concat_file.write_text(
        "\n".join(_concat_line(path) for path in normalized) + "\n",
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


def _normalize_shot(source: Path, output: Path, ffmpeg: str, duration_sec: float = 6) -> Path:
    if not source.is_file():
        raise FileNotFoundError(f"shot video not found: {source}")
    video_filter = (
        f"scale={DELIVERY_WIDTH}:{DELIVERY_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={DELIVERY_WIDTH}:{DELIVERY_HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,fps=30,format=yuv420p"
    )
    command = [ffmpeg, "-y", "-i", source.as_posix(), "-t", str(max(1, duration_sec))]
    if _media_has_audio(source, ffmpeg):
        command += [
            "-vf", video_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", output.as_posix(),
        ]
    else:
        command += [
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-vf", video_filter, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-shortest", "-movflags", "+faststart", output.as_posix(),
        ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode != 0 or not output.is_file():
        raise RuntimeError(f"ffmpeg shot normalization failed: {completed.stderr[-1200:]}")
    return output


def _media_has_audio(path: Path, ffmpeg: str) -> bool:
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path.as_posix()],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return bool(re.search(r"Stream #\d+:\d+.*Audio:", completed.stderr))


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
    return "file '" + path.resolve().as_posix().replace("'", "'\\''") + "'"


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
    match = re.search(r"Video:[^\r\n]*?\b(\d{2,5})x(\d{2,5})\b", text)
    return f"{match.group(1)}x{match.group(2)}" if match else ""


def _parse_fps(text: str) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    return round(float(match.group(1)), 3) if match else 0.0


def _duration_from_shots(shot_report: dict[str, Any]) -> float:
    shots = shot_report.get("shots") or []
    return float(sum(float(shot.get("duration_sec") or 6) for shot in shots) or 6)


def _extract_review_frames(output: Path, frame_dir: Path, ffmpeg: str | None) -> list[Path]:
    if not ffmpeg:
        return []
    frame_dir.mkdir(parents=True, exist_ok=True)
    target = frame_dir / "frame-%02d.jpg"
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-i", output.as_posix(), "-vf", "fps=1/6,scale=360:-2", "-frames:v", "6", "-y", target.as_posix()],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    return sorted(frame_dir.glob("frame-*.jpg")) if completed.returncode == 0 else []

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import imageio_ffmpeg

from tools.base_tool import ToolContext, ToolResult
from tools.collect.tiktok_oembed import TIKTOK_HOSTS
from tools.tool_registry import register_tool


@register_tool("tiktok_video")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    url = str(payload.get("url") or "").strip()
    host = (urlparse(url).hostname or "").lower()
    if urlparse(url).scheme not in {"http", "https"} or host not in TIKTOK_HOSTS:
        return ToolResult.failure("validation", "a supported TikTok URL is required")
    material_dir_value = str(payload.get("material_dir") or "").strip()
    if not material_dir_value:
        return ToolResult.failure("validation", "material_dir is required")
    material_dir = Path(material_dir_value)
    supplied_transcript = str(payload.get("transcript_text") or "").strip()
    if context.mock:
        return ToolResult.success(
            {
                "status": "mock",
                "local_video_path": "",
                "local_cover_path": "",
                "transcript_text": supplied_transcript,
                "transcript_source": "operator" if supplied_transcript else "metadata_only",
                "frame_paths": [],
            },
            meta={"tool": "tiktok_video", "mock": True},
        )

    executable = shutil.which("yt-dlp")
    if not executable:
        return ToolResult.failure("not_configured", "yt-dlp is not installed or not on PATH")
    material_dir.mkdir(parents=True, exist_ok=True)
    command = [
        executable,
        "--no-playlist",
        "--restrict-filenames",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "en,zh-Hans,zh",
        "--sub-format",
        "vtt",
        "-o",
        str(material_dir / "source.%(ext)s"),
    ]
    proxy = str(context.env.get("TIKTOK_PROXY") or "").strip()
    if proxy:
        command.extend(["--proxy", proxy])
    cookies_file = str(context.env.get("TIKTOK_COOKIES_FILE") or "").strip()
    cookies_browser = str(context.env.get("TIKTOK_COOKIES_BROWSER") or "").strip()
    if cookies_file:
        command.extend(["--cookies", cookies_file])
    elif cookies_browser:
        command.extend(["--cookies-from-browser", cookies_browser])
    command.append(url)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
    except subprocess.TimeoutExpired:
        return ToolResult.failure("provider", "TikTok video download timed out after 300 seconds")
    if completed.returncode != 0:
        detail = _last_error(completed.stderr or completed.stdout)
        return ToolResult.failure("provider", f"TikTok video download failed: {detail}")

    video_path = _find_video(material_dir)
    if video_path is None:
        return ToolResult.failure("provider", "yt-dlp completed without a video file")
    subtitle_text = supplied_transcript or _read_subtitles(material_dir)
    transcript_source = "operator" if supplied_transcript else ("subtitle" if subtitle_text else "missing")
    asr_error = ""
    asr_segments: list[dict[str, Any]] = []
    if not subtitle_text:
        from tools.audio import volcengine_asr

        asr = volcengine_asr.execute({"audio_path": video_path.as_posix()}, context)
        if asr.ok:
            subtitle_text = str(asr.data.get("transcript_text") or "").strip()
            asr_segments = list(asr.data.get("segments") or [])
            transcript_source = "volcengine_asr" if subtitle_text else "missing"
        else:
            asr_error = str((asr.error or {}).get("message") or "")
    cover_path = _find_cover(material_dir)
    frame_paths = _extract_frames(video_path, material_dir / "frames")
    return ToolResult.success(
        {
            "status": "downloaded",
            "local_video_path": video_path.as_posix(),
            "local_cover_path": cover_path.as_posix() if cover_path else "",
            "transcript_text": subtitle_text,
            "transcript_source": transcript_source,
            "transcript_segments": asr_segments,
            "asr_error": asr_error,
            "frame_paths": [path.as_posix() for path in frame_paths],
        },
        meta={"tool": "tiktok_video", "mock": False, "frame_count": len(frame_paths), "transcript_source": transcript_source},
    )


def _find_video(material_dir: Path) -> Path | None:
    excluded = {".json", ".vtt", ".srt", ".part", ".ytdl"}
    files = [path for path in material_dir.glob("source.*") if path.suffix.casefold() not in excluded]
    return max(files, key=lambda path: path.stat().st_size) if files else None


def _find_cover(material_dir: Path) -> Path | None:
    covers = [path for path in material_dir.glob("source.*") if path.suffix.casefold() in {".jpg", ".jpeg", ".png", ".webp"}]
    return max(covers, key=lambda path: path.stat().st_size) if covers else None


def _read_subtitles(material_dir: Path) -> str:
    for path in sorted(material_dir.glob("source*.vtt")):
        lines: list[str] = []
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line == "WEBVTT" or "-->" in line or line.isdigit():
                continue
            line = re.sub(r"<[^>]+>", "", line).strip()
            if line and (not lines or lines[-1] != line):
                lines.append(line)
        if lines:
            return " ".join(lines)[:12000]
    return ""


def _extract_frames(video_path: Path, frame_dir: Path) -> list[Path]:
    frame_dir.mkdir(parents=True, exist_ok=True)
    output = frame_dir / "frame-%02d.jpg"
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(video_path),
        "-vf",
        "fps=1/6,scale=360:-2",
        "-frames:v",
        "5",
        "-y",
        str(output),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    return sorted(frame_dir.glob("frame-*.jpg")) if completed.returncode == 0 else []


def _last_error(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return (lines[-1] if lines else "unknown provider error")[:500]

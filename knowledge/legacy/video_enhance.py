"""成片前逐镜增强（去闪烁/稳定）— 默认关闭，失败降级。"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from .video_assemble import find_ffmpeg


def enhance_enabled() -> bool:
    return (os.getenv("AI_VIDEO_ENHANCE") or "0").strip().lower() in ("1", "true", "yes", "on")


def enhance_shot_clips(project: Path, *, broll_dir: Path | None = None) -> dict[str, Any]:
    """对 broll 目录下 mp4 做轻量稳定；失败时跳过单镜。"""
    if not enhance_enabled():
        return {"ok": True, "skipped": True, "message": "AI_VIDEO_ENHANCE 未开启"}
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"ok": True, "skipped": True, "message": "ffmpeg 不可用，跳过增强"}

    broll = broll_dir or (project / "broll")
    if not broll.is_dir():
        return {"ok": True, "skipped": True, "message": "无 broll 目录"}

    enhanced = 0
    errors: list[str] = []
    for mp4 in sorted(broll.glob("shot-*.mp4")):
        tmp = mp4.with_suffix(".enhanced.mp4")
        try:
            proc = subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-i",
                    str(mp4),
                    "-vf",
                    "deshake",
                    "-c:a",
                    "copy",
                    str(tmp),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=180,
            )
            if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1000:
                errors.append(f"{mp4.name}: {((proc.stderr or '')[-120:])}")
                tmp.unlink(missing_ok=True)
                continue
            mp4.unlink(missing_ok=True)
            tmp.rename(mp4)
            enhanced += 1
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{mp4.name}: {exc}")
            tmp.unlink(missing_ok=True)

    return {
        "ok": True,
        "enhanced": enhanced,
        "errors": errors,
        "message": f"已增强 {enhanced} 镜" if enhanced else "无镜增强或全部跳过",
    }

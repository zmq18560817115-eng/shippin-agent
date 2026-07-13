"""将 broll/shot-N.mp4 按分镜顺序拼接为成片 final-video.mp4。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import write_json


def _ffmpeg_from_imageio() -> str | None:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    return None


def _bootstrap_imageio_ffmpeg() -> bool:
    """在交付引擎子进程内尝试 pip 安装 imageio-ffmpeg（拼接时自动修复）。"""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "imageio-ffmpeg"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        return proc.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def find_ffmpeg() -> str | None:
    for name in ("ffmpeg", "ffmpeg.exe"):
        found = shutil.which(name)
        if found and Path(found).is_file():
            return found
    exe = _ffmpeg_from_imageio()
    if exe:
        return exe
    if _bootstrap_imageio_ffmpeg():
        return _ffmpeg_from_imageio()
    return None


def _shot_sort_key(path: Path) -> int:
    m = re.search(r"shot-(\d+)", path.name)
    return int(m.group(1)) if m else 0


def list_shot_mp4s(project: Path) -> list[Path]:
    broll = project / "broll"
    if not broll.is_dir():
        return []
    return sorted(broll.glob("shot-*.mp4"), key=_shot_sort_key)


def assemble_storyboard_video(project: Path, *, min_shots: int = 1) -> dict[str, Any]:
    """拼接分镜 mp4 → broll/final-video.mp4。返回状态 dict。"""
    shots = list_shot_mp4s(project)
    if len(shots) < min_shots:
        return {
            "ok": False,
            "message": f"分镜视频不足（{len(shots)}/{min_shots}），请先生成各镜 mp4",
            "shots_used": len(shots),
            "file": None,
        }

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {
            "ok": False,
            "message": (
                "未找到 ffmpeg。请关闭工作台后重新运行「启动工作台.cmd」或「检查开发环境.cmd」"
                "（将自动安装 imageio-ffmpeg），再点「重新合成」"
            ),
            "shots_used": len(shots),
            "file": None,
        }

    broll = project / "broll"
    broll.mkdir(parents=True, exist_ok=True)
    output = broll / "final-video.mp4"
    meta_path = broll / "final-video-meta.json"

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tmp:
        for mp4 in shots:
            # concat demuxer 需要 escaped paths
            escaped = mp4.resolve().as_posix().replace("'", "'\\''")
            tmp.write(f"file '{escaped}'\n")
        list_file = tmp.name

    try:
        cmd_copy = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_file,
            "-c",
            "copy",
            str(output),
        ]
        proc = subprocess.run(cmd_copy, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode != 0 or not output.is_file() or output.stat().st_size < 1000:
            cmd_reencode = [
                ffmpeg,
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                list_file,
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-crf",
                "23",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(output),
            ]
            proc = subprocess.run(
                cmd_reencode, capture_output=True, text=True, encoding="utf-8", errors="replace"
            )
        if proc.returncode != 0 or not output.is_file():
            tail = (proc.stderr or proc.stdout or "ffmpeg 失败")[-600:].strip()
            return {
                "ok": False,
                "message": "分镜已生成，成片拼接未完成，请检查 ffmpeg 后重试",
                "detail": tail,
                "shots_used": len(shots),
                "file": None,
            }
    finally:
        Path(list_file).unlink(missing_ok=True)

    meta = {
        "assembled_at": datetime.now(timezone.utc).isoformat(),
        "shots": [{"number": _shot_sort_key(p), "file": p.relative_to(project).as_posix()} for p in shots],
        "output": "broll/final-video.mp4",
        "bytes": output.stat().st_size,
        "ffmpeg": ffmpeg,
    }
    write_json(meta_path, meta)
    return {
        "ok": True,
        "message": f"已拼接 {len(shots)} 镜 → final-video.mp4",
        "shots_used": len(shots),
        "file": "broll/final-video.mp4",
        "bytes": meta["bytes"],
        "meta": meta,
    }

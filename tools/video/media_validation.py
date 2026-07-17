from __future__ import annotations

import subprocess
from pathlib import Path

from tools.video.ffmpeg_compose import _find_ffmpeg


def is_playable_mp4(path: Path) -> bool:
    """Validate that an MP4 contains at least one decodable video frame."""
    if not path.is_file() or path.stat().st_size < 10_000:
        return False
    try:
        with path.open("rb") as handle:
            header = handle.read(32)
    except OSError:
        return False
    if b"ftyp" not in header:
        return False
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False
    try:
        completed = subprocess.run(
            [ffmpeg, "-v", "error", "-i", path.as_posix(), "-map", "0:v:0", "-frames:v", "1", "-f", "null", "-"],
            capture_output=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0

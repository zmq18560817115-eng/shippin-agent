from __future__ import annotations

import importlib.util
import shutil
import sys


def yt_dlp_command() -> list[str] | None:
    executable = shutil.which("yt-dlp")
    if executable:
        return [executable]
    if importlib.util.find_spec("yt_dlp") is not None:
        return [sys.executable, "-m", "yt_dlp"]
    return None


def yt_dlp_available() -> bool:
    return yt_dlp_command() is not None

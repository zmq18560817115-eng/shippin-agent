from __future__ import annotations

import importlib.util
import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def command_version(command: str, args: list[str]) -> dict[str, object]:
    executable = shutil.which(command)
    if not executable:
        return {"ok": False, "detail": "not found"}
    result = subprocess.run([executable, *args], capture_output=True, text=True, timeout=20)
    line = (result.stdout or result.stderr).splitlines()
    return {"ok": result.returncode == 0, "detail": line[0] if line else executable}


def application_ffmpeg() -> dict[str, object]:
    executable = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    source = "system PATH"
    if not executable:
        try:
            import imageio_ffmpeg

            executable = imageio_ffmpeg.get_ffmpeg_exe()
            source = "imageio-ffmpeg bundle"
        except Exception:
            executable = None
    if not executable:
        return {"ok": False, "detail": "not found in PATH or imageio-ffmpeg"}
    result = subprocess.run([executable, "-version"], capture_output=True, text=True, timeout=20)
    first_line = (result.stdout or result.stderr).splitlines()
    return {
        "ok": result.returncode == 0,
        "detail": f"{source}: {first_line[0] if first_line else executable}",
        "path": executable,
    }


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def writable_directory(path: Path) -> dict[str, object]:
    path.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".preflight-", delete=True):
            pass
    except OSError as exc:
        return {"ok": False, "detail": str(exc), "path": str(path)}
    return {"ok": True, "detail": "writable", "path": str(path)}


def sqlite_check(path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with sqlite3.connect(path) as conn:
            mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            conn.execute("CREATE TABLE IF NOT EXISTS deployment_preflight (checked_at TEXT)")
        return {"ok": mode.casefold() == "wal", "detail": f"journal_mode={mode}", "path": str(path)}
    except sqlite3.Error as exc:
        return {"ok": False, "detail": str(exc), "path": str(path)}


def playwright_check() -> dict[str, object]:
    if importlib.util.find_spec("playwright") is None:
        return {"ok": False, "detail": "python package not installed"}
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            browser.close()
        return {"ok": True, "detail": "chromium launched"}
    except Exception as exc:  # Browser installation errors vary by platform.
        return {"ok": False, "detail": str(exc).splitlines()[0]}


def security_checks() -> dict[str, dict[str, object]]:
    auth_enabled = os.environ.get("VAF_AUTH_ENABLED", "").strip().casefold() in {"1", "true", "yes", "on"}
    secret = os.environ.get("VAF_SESSION_SECRET", "").strip()
    cookie_secure = os.environ.get("VAF_COOKIE_SECURE", "").strip().casefold() in {"1", "true", "yes", "on"}
    return {
        "auth_enabled": {"ok": auth_enabled, "detail": "enabled" if auth_enabled else "intranet deployment must enable authentication"},
        "session_secret": {"ok": (not auth_enabled) or len(secret) >= 32, "detail": "configured" if len(secret) >= 32 else "VAF_SESSION_SECRET must contain at least 32 characters when authentication is enabled"},
        "cookie_secure": {"ok": True, "detail": "enabled" if cookie_secure else ("warning: set VAF_COOKIE_SECURE=true behind HTTPS" if auth_enabled else "not applicable while authentication is disabled")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a video-agent-factory deployment host.")
    parser.add_argument("--env-file", default=".env.local", help="Environment file relative to the repository root")
    args = parser.parse_args()
    env_path = Path(args.env_file)
    if not env_path.is_absolute():
        env_path = ROOT / env_path
    load_env_file(env_path)
    data_root = Path(os.environ.get("VAF_DATA_ROOT", ROOT / "data"))
    db_path = Path(os.environ.get("VAF_DB_PATH", data_root / "video_agent_factory.db"))
    cookies = os.environ.get("TIKTOK_COOKIES_FILE", "").strip()
    checks = {
        "ffmpeg": application_ffmpeg(),
        "system_ffprobe": command_version("ffprobe", ["-version"]),
        "yt_dlp": command_version("yt-dlp", ["--version"]),
        "playwright": playwright_check(),
        "database": sqlite_check(db_path),
        "materials_volume": writable_directory(data_root / "01_素材库"),
        "runs_volume": writable_directory(Path(os.environ.get("VAF_RUNS_ROOT", data_root / "runs"))),
        "cookies": {
            "ok": bool(cookies and Path(cookies).is_file()),
            "detail": "configured file exists" if cookies and Path(cookies).is_file() else "TIKTOK_COOKIES_FILE is missing or invalid",
        },
        "doubao_key": {"ok": bool(os.environ.get("DOUBAO_API_KEY")), "detail": "configured" if os.environ.get("DOUBAO_API_KEY") else "missing"},
        "seedance_key": {"ok": bool(os.environ.get("SEEDANCE_API_KEY")), "detail": "configured" if os.environ.get("SEEDANCE_API_KEY") else "missing"},
    }
    checks.update(security_checks())
    required = ["ffmpeg", "yt_dlp", "playwright", "database", "materials_volume", "runs_volume", "auth_enabled", "session_secret"]
    report = {
        "status": "pass" if all(bool(checks[name]["ok"]) for name in required) else "fail",
        "checks": checks,
        "note": "Cookies and model keys are reported separately because their necessity depends on the enabled collector and run mode.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

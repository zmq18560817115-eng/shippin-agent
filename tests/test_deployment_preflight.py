from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts import deployment_preflight


ROOT = Path(__file__).resolve().parents[1]


def test_deployment_preflight_supports_direct_script_execution() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "deployment_preflight.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 0, result.stderr
    assert "Validate a video-agent-factory deployment host" in result.stdout


def test_security_preflight_requires_intranet_auth(monkeypatch) -> None:
    monkeypatch.setenv("VAF_AUTH_ENABLED", "false")
    checks = deployment_preflight.security_checks()

    assert checks["auth_enabled"]["ok"] is False
    assert "must enable authentication" in str(checks["auth_enabled"]["detail"])


def test_security_preflight_requires_long_secret_when_auth_enabled(monkeypatch) -> None:
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_SESSION_SECRET", "short")
    checks = deployment_preflight.security_checks()

    assert checks["auth_enabled"]["ok"] is True
    assert checks["session_secret"]["ok"] is False


def test_command_version_reports_blocked_executable_without_crashing(monkeypatch) -> None:
    monkeypatch.setattr(deployment_preflight.shutil, "which", lambda command: "blocked-tool.exe")
    monkeypatch.setattr(
        deployment_preflight.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("blocked by application control")),
    )

    result = deployment_preflight.command_version("yt-dlp", ["--version"])

    assert result["ok"] is False
    assert "blocked by application control" in str(result["detail"])

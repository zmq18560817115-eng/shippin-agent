from __future__ import annotations

from scripts import deployment_preflight


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

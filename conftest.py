from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_auth_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep developer deployment settings from changing API test behavior."""
    monkeypatch.setenv("VAF_AUTH_ENABLED", "false")

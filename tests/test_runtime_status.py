from __future__ import annotations

from fastapi.testclient import TestClient

from orchestrator.api import app


def test_runtime_status_never_exposes_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("DOUBAO_API_KEY", "private-doubao-value")
    monkeypatch.delenv("SEEDANCE_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/v2/runtime")
    assert response.status_code == 200
    payload = response.json()
    assert payload["real_ready"] is False
    assert payload["providers"]["doubao"]["configured"] is True
    assert payload["providers"]["seedance"]["configured"] is False
    assert "private-doubao-value" not in response.text

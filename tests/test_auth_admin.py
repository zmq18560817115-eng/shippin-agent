from fastapi.testclient import TestClient

from orchestrator.api import app


def test_local_portals_are_available_without_auth(monkeypatch):
    monkeypatch.delenv("VAF_AUTH_ENABLED", raising=False)
    with TestClient(app) as client:
        assert client.get("/").history[0].status_code == 303
        assert client.get("/login").status_code == 200
        response = client.post(
            "/api/v2/auth/login",
            json={"username": "", "password": "", "portal": "operator"},
        )
        assert response.status_code == 200
        assert response.json()["redirect"] == "/workbench"
        assert client.get("/api/v2/auth/session").json()["role"] == "operator"


def test_admin_endpoint_requires_admin_role(monkeypatch):
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_OPERATOR_USER", "operator")
    monkeypatch.setenv("VAF_OPERATOR_PASSWORD", "operator-pass")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")

    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v2/admin/summary").status_code == 401

    with TestClient(app) as operator:
        login = operator.post(
            "/api/v2/auth/login",
            json={"username": "operator", "password": "operator-pass", "portal": "operator"},
        )
        assert login.status_code == 200
        assert operator.get("/api/v2/admin/summary").status_code == 403

    with TestClient(app) as admin:
        login = admin.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "admin-pass", "portal": "admin"},
        )
        assert login.status_code == 200
        summary = admin.get("/api/v2/admin/summary")
        assert summary.status_code == 200
        assert summary.json()["status"] == "ok"
        assert "storage_bytes" in summary.json()

from fastapi.testclient import TestClient

from orchestrator.api import app
from orchestrator import queue


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


def test_admin_endpoint_requires_admin_role(monkeypatch, tmp_path):
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "auth.db"))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
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
        assert len(summary.json()["analytics"]["daily"]) == 7
        assert summary.json()["analytics"]["project_status"] == summary.json()["projects"]


def test_admin_summary_separates_standalone_runs_from_production_projects(monkeypatch, tmp_path):
    db_path = tmp_path / "admin-counts.db"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    queue.init_db(db_path=db_path)
    queue.ensure_project("production-1", product_id="product", db_path=db_path)
    queue.ensure_project(
        "scratch-1",
        product_id="product",
        payload={"standalone": True, "standalone_action": "script"},
        db_path=db_path,
    )
    standalone_task = queue.enqueue_task(
        project_id="scratch-1", stage="script", agent="script", db_path=db_path
    )
    queue.mark_task_status(
        standalone_task, "failed", error={"message": "standalone failure"}, db_path=db_path
    )

    with TestClient(app) as admin:
        assert admin.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "admin-pass", "portal": "admin"},
        ).status_code == 200
        summary = admin.get("/api/v2/admin/summary").json()

    assert sum(summary["projects"].values()) == 1
    assert summary["standalone_run_count"] == 1
    assert summary["tasks"].get("failed", 0) == 0
    assert summary["recent_failures"] == []


def test_admin_can_ignore_failed_task_with_audit_event(monkeypatch, tmp_path):
    db_path = tmp_path / "ignore-task.db"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(project_id="failed-project", stage="analysis", agent="analysis", db_path=db_path)
    queue.mark_task_status(task_id, "failed", error={"message": "模型调用失败"}, db_path=db_path)

    with TestClient(app) as admin:
        assert admin.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "admin-pass", "portal": "admin"},
        ).status_code == 200
        summary = admin.get("/api/v2/admin/summary").json()
        assert summary["recent_failures"][0]["task_id"] == task_id
        ignored = admin.post(f"/api/v2/admin/tasks/{task_id}/ignore", json={"reason": "历史测试任务"})
        assert ignored.status_code == 200
        assert queue.get_task(task_id, db_path=db_path).status == "cancelled"
        events = queue.list_events(event_type="task.ignored", db_path=db_path)
        assert events[0]["task_id"] == task_id


def test_admin_can_assign_failed_task_to_active_user(monkeypatch, tmp_path):
    db_path = tmp_path / "assign-task.db"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    queue.init_db(db_path=db_path)
    task_id = queue.enqueue_task(project_id="assigned-project", stage="analysis", agent="analysis", db_path=db_path)
    queue.mark_task_status(task_id, "failed", error={"message": "模型调用失败"}, db_path=db_path)

    with TestClient(app) as admin:
        assert admin.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "admin-pass", "portal": "admin"},
        ).status_code == 200
        assigned = admin.post(f"/api/v2/admin/tasks/{task_id}/assign", json={"assignee": "admin"})
        assert assigned.status_code == 200
        assert assigned.json()["assignee"] == "admin"
        summary = admin.get("/api/v2/admin/summary").json()
        assert summary["recent_failures"][0]["assignee"] == "admin"
        events = queue.list_events(event_type="task.assigned", db_path=db_path)
        assert events[0]["task_id"] == task_id

        missing = admin.post(f"/api/v2/admin/tasks/{task_id}/assign", json={"assignee": "missing-user"})
        assert missing.status_code == 422


def test_admin_can_create_and_disable_database_user(monkeypatch, tmp_path):
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "users.db"))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    monkeypatch.delenv("VAF_OPERATOR_USER", raising=False)
    monkeypatch.delenv("VAF_OPERATOR_PASSWORD", raising=False)

    with TestClient(app) as admin:
        assert admin.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "admin-pass", "portal": "admin"},
        ).status_code == 200
        created = admin.post(
            "/api/v2/admin/users",
            json={"username": "editor", "password": "editor-pass", "role": "operator", "display_name": "内容编辑"},
        )
        assert created.status_code == 200
        user = created.json()["user"]
        assert "password_hash" not in user
        assert user["username"] == "editor"

        disabled = admin.patch(f"/api/v2/admin/users/{user['id']}", json={"status": "disabled"})
        assert disabled.status_code == 200
        assert disabled.json()["user"]["status"] == "disabled"

    with TestClient(app) as editor:
        denied = editor.post(
            "/api/v2/auth/login",
            json={"username": "editor", "password": "editor-pass", "portal": "operator"},
        )
        assert denied.status_code == 401


def test_disabling_user_revokes_existing_session(monkeypatch, tmp_path):
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "revoked.db"))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    monkeypatch.delenv("VAF_OPERATOR_USER", raising=False)
    monkeypatch.delenv("VAF_OPERATOR_PASSWORD", raising=False)

    with TestClient(app) as admin, TestClient(app) as editor:
        admin.post("/api/v2/auth/login", json={"username": "admin", "password": "admin-pass", "portal": "admin"})
        created = admin.post(
            "/api/v2/admin/users",
            json={"username": "editor", "password": "editor-pass", "role": "operator"},
        ).json()["user"]
        assert editor.post(
            "/api/v2/auth/login",
            json={"username": "editor", "password": "editor-pass", "portal": "operator"},
        ).status_code == 200
        assert editor.get("/api/v2/pipeline").status_code == 200

        assert admin.patch(f"/api/v2/admin/users/{created['id']}", json={"status": "disabled"}).status_code == 200
        assert editor.get("/api/v2/pipeline").status_code == 401


def test_last_active_admin_cannot_be_disabled(monkeypatch, tmp_path):
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "last-admin.db"))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    monkeypatch.delenv("VAF_OPERATOR_USER", raising=False)
    monkeypatch.delenv("VAF_OPERATOR_PASSWORD", raising=False)

    with TestClient(app) as admin:
        admin.post("/api/v2/auth/login", json={"username": "admin", "password": "admin-pass", "portal": "admin"})
        current = admin.get("/api/v2/admin/users").json()["items"][0]
        denied = admin.patch(f"/api/v2/admin/users/{current['id']}", json={"status": "disabled"})
        assert denied.status_code == 422


def test_registration_request_needs_admin_approval(monkeypatch, tmp_path):
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "registration.db"))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SELF_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")
    monkeypatch.delenv("VAF_OPERATOR_USER", raising=False)
    monkeypatch.delenv("VAF_OPERATOR_PASSWORD", raising=False)

    with TestClient(app) as anonymous:
        submitted = anonymous.post(
            "/api/v2/auth/register",
            json={"username": "new-editor", "display_name": "New Editor", "password": "new-editor-pass"},
        )
        assert submitted.status_code == 200, submitted.text
        request_id = submitted.json()["registration"]["id"]
        denied = anonymous.post(
            "/api/v2/auth/login",
            json={"username": "new-editor", "password": "new-editor-pass", "portal": "operator"},
        )
        assert denied.status_code == 401

    with TestClient(app) as admin:
        assert admin.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "admin-pass", "portal": "admin"},
        ).status_code == 200
        items = admin.get("/api/v2/admin/registration-requests")
        assert items.status_code == 200
        assert items.json()["items"][0]["status"] == "pending"
        approved = admin.post(f"/api/v2/admin/registration-requests/{request_id}/approve", json={})
        assert approved.status_code == 200, approved.text
        assert approved.json()["registration"]["status"] == "approved"

    with TestClient(app) as editor:
        accepted = editor.post(
            "/api/v2/auth/login",
            json={"username": "new-editor", "password": "new-editor-pass", "portal": "operator"},
        )
        assert accepted.status_code == 200


def test_login_and_registration_are_rate_limited(monkeypatch, tmp_path):
    from orchestrator import api

    api.LOGIN_FAILURES.clear()
    api.REGISTRATION_ATTEMPTS.clear()
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "rate-limit.db"))
    monkeypatch.setenv("VAF_AUTH_ENABLED", "true")
    monkeypatch.setenv("VAF_COOKIE_SECURE", "false")
    monkeypatch.setenv("VAF_SELF_REGISTRATION_ENABLED", "true")
    monkeypatch.setenv("VAF_SESSION_SECRET", "test-session-secret-with-32-characters")
    monkeypatch.setenv("VAF_ADMIN_USER", "admin")
    monkeypatch.setenv("VAF_ADMIN_PASSWORD", "admin-pass")

    with TestClient(app) as client:
        for _ in range(5):
            assert client.post("/api/v2/auth/login", json={"username": "admin", "password": "wrong", "portal": "admin"}).status_code == 401
        assert client.post("/api/v2/auth/login", json={"username": "admin", "password": "wrong", "portal": "admin"}).status_code == 429
        for index in range(5):
            assert client.post("/api/v2/auth/register", json={"username": f"user-{index}", "password": "password-123"}).status_code == 200
        assert client.post("/api/v2/auth/register", json={"username": "user-over-limit", "password": "password-123"}).status_code == 429


def test_real_pipeline_requires_model_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "real-preflight.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.delenv("DOUBAO_API_KEY", raising=False)
    monkeypatch.delenv("SEEDANCE_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/v2/pipeline/run", json={"product_id": "便携恒温杯", "mock": False})
    assert response.status_code == 422
    assert "DOUBAO_API_KEY" in response.json()["detail"]

from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from orchestrator import cost_tracker, queue
from orchestrator.api import app
from tools.base_tool import ToolResult


@pytest.fixture(autouse=True)
def runtime_status_uses_explicit_no_auth_test_mode(monkeypatch):
    monkeypatch.setenv("VAF_AUTH_ENABLED", "false")


def test_runtime_status_never_exposes_secret_values(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "empty-runtime.sqlite3"
    monkeypatch.setattr("orchestrator.api._db_path", lambda: db_path)
    queue.init_db(db_path=db_path)
    monkeypatch.setenv("DOUBAO_API_KEY", "private-doubao-value")
    monkeypatch.delenv("SEEDANCE_API_KEY", raising=False)
    monkeypatch.delenv("VAF_LOCAL_ASR_ENABLED", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/v2/runtime")
    assert response.status_code == 200
    payload = response.json()
    assert payload["real_ready"] is False
    assert payload["providers"]["doubao"]["configured"] is True
    assert payload["providers"]["doubao"]["state"] == "configured_unverified"
    assert payload["providers"]["doubao"]["operational"] is False
    assert payload["providers"]["seedance"]["configured"] is False
    assert "tiktok_video" in payload["providers"]
    assert payload["providers"]["speech_to_text"]["configured"] is False
    assert "tiktok_keyword_crawler" in payload["providers"]
    assert "tiktok_api" in payload["providers"]
    assert "installed" in payload["providers"]["tiktok_api"]
    assert "private-doubao-value" not in response.text


def test_runtime_reports_local_asr_without_cloud_secret(monkeypatch) -> None:
    monkeypatch.delenv("VOLCENGINE_ASR_API_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_ASR_APP_KEY", raising=False)
    monkeypatch.delenv("VOLCENGINE_ASR_ACCESS_KEY", raising=False)
    monkeypatch.setenv("VAF_LOCAL_ASR_ENABLED", "true")

    with TestClient(app) as client:
        payload = client.get("/api/v2/runtime").json()

    assert payload["providers"]["speech_to_text"]["configured"] is True
    assert payload["providers"]["speech_to_text"]["mode"] == "faster_whisper_local"


def test_runtime_distinguishes_optional_and_builtin_collector_backends(monkeypatch) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        payload = client.get("/api/v2/runtime").json()
    backends = {item["id"]: item for item in payload["collector_backends"]}
    assert backends["apify"]["state"] == "optional_disabled"
    assert backends["apify"]["optional"] is True
    assert backends["manual_url"]["configured"] is True
    assert "build_version" in payload


def test_tiktok_runtime_probe_persists_friendly_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.api._runtime_probe_path", lambda: tmp_path / "runtime-probes.json")
    monkeypatch.setattr(
        "orchestrator.api.tool_registry.execute_tool",
        lambda *args, **kwargs: ToolResult.failure("provider", "Page.goto: Timeout 30000ms exceeded"),
    )
    with TestClient(app) as client:
        response = client.post("/api/v2/admin/runtime/probe", json={"provider": "tiktok_api"})
        runtime = client.get("/api/v2/runtime").json()
    assert response.status_code == 200
    assert response.json()["ok"] is False
    assert "外网" in response.json()["probe"]["detail"]
    assert runtime["providers"]["tiktok_api"]["state"] == "error"


def test_admin_can_replace_netscape_tiktok_cookies_without_exposing_values(tmp_path, monkeypatch) -> None:
    target = tmp_path / "secrets" / "tiktok-cookies.txt"
    monkeypatch.setenv("TIKTOK_COOKIES_FILE", str(target))
    content = "# Netscape HTTP Cookie File\n.tiktok.com\tTRUE\t/\tTRUE\t0\tmsToken\tsecret-value"

    with TestClient(app) as client:
        response = client.post("/api/v2/admin/runtime/cookies", json={"cookies_text": content})
        runtime = client.get("/api/v2/runtime")

    assert response.status_code == 200, response.text
    assert target.read_text(encoding="utf-8").startswith("# Netscape HTTP Cookie File")
    assert runtime.json()["deployment"]["tiktok_cookies"]["ready"] is True
    assert "secret-value" not in runtime.text
    assert "detail" in response.json()


def test_admin_rejects_non_netscape_cookie_upload() -> None:
    with TestClient(app) as client:
        response = client.post("/api/v2/admin/runtime/cookies", json={"cookies_text": "msToken=secret"})

    assert response.status_code == 422
    assert "Netscape" in response.json()["detail"]


def test_auto_runtime_probe_uses_tiktok_api_when_browser_search_is_not_configured(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("orchestrator.api._runtime_probe_path", lambda: tmp_path / "runtime-probes.json")
    monkeypatch.setattr("tools.collect.tiktok_browser_search.configured", lambda env: False)
    captured: dict[str, object] = {}

    def execute_tool(name, payload, **kwargs):
        captured.update(payload)
        return ToolResult.success({"items": [{"url": "https://www.tiktok.com/@demo/video/1"}]})

    monkeypatch.setattr("orchestrator.api.tool_registry.execute_tool", execute_tool)
    with TestClient(app) as client:
        response = client.post("/api/v2/admin/runtime/probe", json={"provider": "auto"})

    assert response.status_code == 200
    assert response.json()["provider"] == "tiktok_api"
    assert captured["provider"] == "tiktok_api"


def test_runtime_uses_successful_real_model_calls_as_readiness_evidence(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "runtime.sqlite3"
    monkeypatch.setattr("orchestrator.api._db_path", lambda: db_path)
    monkeypatch.setenv("DOUBAO_API_KEY", "configured-text-key")
    monkeypatch.setenv("SEEDANCE_API_KEY", "configured-video-key")
    queue.init_db(db_path=db_path)
    cost_tracker.reconcile(
        project_id="real-evidence",
        agent="script",
        tool="doubao_script",
        cost_cny=0.01,
        model="doubao-text",
        meta={"mock": False},
        db_path=db_path,
    )
    cost_tracker.reconcile(
        project_id="real-evidence",
        agent="media",
        tool="seedance_shot",
        cost_cny=1.0,
        model="seedance-video",
        meta={"mock": False},
        db_path=db_path,
    )

    with TestClient(app) as client:
        payload = client.get("/api/v2/runtime").json()

    assert payload["providers"]["doubao"]["state"] == "ready"
    assert payload["providers"]["seedance"]["state"] == "ready"
    assert "真实调用已验证" in payload["providers"]["doubao"]["detail"]
    assert "configured-text-key" not in str(payload)

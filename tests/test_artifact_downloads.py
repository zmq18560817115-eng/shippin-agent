from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator.api import app


def test_standalone_storyboard_builds_script_foundation_and_downloads(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))

    with TestClient(app) as client:
        response = client.post(
            "/api/v2/agents/run",
            json={
                "action": "storyboard",
                "product_id": "便携恒温杯",
                "prompt": "夜间照护者准备奶液，展示正确倒液流程",
                "mock": True,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        project_id = payload["project_id"]
        assert payload["artifact_name"] == "shot_plan"
        assert payload["download_url"].endswith("/shot_plan/download")
        assert (tmp_path / "runs" / project_id / "artifacts" / "script_copy.json").is_file()

        download = client.get(payload["download_url"])
        assert download.status_code == 200
        assert "attachment" in download.headers["content-disposition"]
        assert download.json()["project_id"] == project_id


def test_runtime_lists_collector_fallbacks(monkeypatch) -> None:
    monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
    with TestClient(app) as client:
        response = client.get("/api/v2/runtime")
    assert response.status_code == 200
    backend_ids = [item["id"] for item in response.json()["collector_backends"]]
    assert backend_ids == ["tiktok_api", "apify", "yt_dlp", "manual_url"]

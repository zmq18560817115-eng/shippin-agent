from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator.api import app
from tools.base_tool import ToolContext
from tools.collect import tiktok_crawler


def test_keyword_crawler_requires_provider_token() -> None:
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "heated cup", "limit": 2},
        ToolContext(mock=False, env={}),
    )
    assert result.ok is False
    assert result.error["category"] == "not_configured"
    assert "APIFY_API_TOKEN" in result.error["message"]


def test_mock_crawler_discovers_requested_number() -> None:
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "heated cup", "limit": 3},
        ToolContext(mock=True),
    )
    assert result.ok is True
    assert len(result.data["items"]) == 3
    assert all("tiktok.com" in item["url"] for item in result.data["items"])


def test_crawl_endpoint_creates_projects_for_discovered_videos(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "queue.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(tmp_path / "materials"))
    with TestClient(app) as client:
        response = client.post(
            "/api/v2/collect/tiktok/crawl",
            json={
                "target_type": "keyword",
                "target": "heated cup",
                "limit": 2,
                "product_id": "便携恒温杯",
                "mock": True,
            },
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["discovered_count"] == 2
    assert payload["completed_count"] == 2
    assert payload["failed_count"] == 0
    assert all(item["stage"] == "script_gate" for item in payload["results"])

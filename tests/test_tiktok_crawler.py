from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator.api import app
from tools.base_tool import ToolContext
from tools.collect import tiktok_crawler
from tools.collect import tiktok_api_adapter


def test_keyword_crawler_requires_provider_token() -> None:
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "heated cup", "limit": 2},
        ToolContext(mock=False, env={}),
    )
    assert result.ok is False
    assert result.error["category"] == "not_configured"
    assert "APIFY_API_TOKEN" in result.error["message"]
    assert "TIKTOK_MS_TOKEN" in result.error["message"]


def test_auto_provider_prefers_apify_for_keyword(monkeypatch) -> None:
    monkeypatch.setattr(tiktok_crawler, "_discover_keyword", lambda keyword, limit, token: [{"url": "https://www.tiktok.com/@demo/video/1"}])
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "heated cup", "limit": 1},
        ToolContext(mock=False, env={"APIFY_API_TOKEN": "token"}),
    )
    assert result.ok is True
    assert result.data["provider"] == "apify"


def test_tiktok_api_provider_is_isolated_and_normalized(monkeypatch) -> None:
    monkeypatch.setattr(
        tiktok_api_adapter,
        "discover",
        lambda **kwargs: [{"url": "https://www.tiktok.com/@brand/video/42", "caption": "demo"}],
    )
    result = tiktok_crawler.execute(
        {"target_type": "hashtag", "provider": "tiktok_api", "target": "heatedcup", "limit": 1},
        ToolContext(mock=False, env={"TIKTOK_MS_TOKEN": "secret"}),
    )
    assert result.ok is True
    assert result.data["provider"] == "tiktok_api"
    assert result.data["items"][0]["caption"] == "demo"


def test_tiktok_api_video_normalization() -> None:
    item = tiktok_api_adapter._normalize_video(
        {
            "id": "123",
            "desc": "恒温杯演示",
            "author": {"uniqueId": "brand"},
            "stats": {"diggCount": 9, "playCount": 20},
        }
    )
    assert item is not None
    assert item["url"] == "https://www.tiktok.com/@brand/video/123"
    assert item["like_count"] == 9
    assert item["play_count"] == 20


def test_auto_account_falls_back_to_ytdlp_when_tiktok_api_fails(monkeypatch) -> None:
    monkeypatch.setattr(tiktok_api_adapter, "configured", lambda env: True)
    monkeypatch.setattr(tiktok_api_adapter, "discover", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(tiktok_crawler.shutil, "which", lambda name: "yt-dlp.exe")
    monkeypatch.setattr(
        tiktok_crawler,
        "_discover_account",
        lambda url, limit: [{"url": "https://www.tiktok.com/@brand/video/99"}],
    )
    result = tiktok_crawler.execute(
        {"target_type": "account", "provider": "auto", "target": "https://www.tiktok.com/@brand", "limit": 1},
        ToolContext(mock=False, env={"TIKTOK_MS_TOKEN": "secret"}),
    )
    assert result.ok is True
    assert result.data["provider"] == "yt_dlp_fallback"


def test_explicit_ytdlp_provider_does_not_enter_tiktok_api(monkeypatch) -> None:
    monkeypatch.setattr(tiktok_api_adapter, "discover", lambda **kwargs: (_ for _ in ()).throw(AssertionError("wrong backend")))
    monkeypatch.setattr(tiktok_crawler.shutil, "which", lambda name: "yt-dlp.exe")
    monkeypatch.setattr(
        tiktok_crawler,
        "_discover_account",
        lambda url, limit: [{"url": "https://www.tiktok.com/@brand/video/100"}],
    )
    result = tiktok_crawler.execute(
        {"target_type": "account", "provider": "yt_dlp", "target": "https://www.tiktok.com/@brand", "limit": 1},
        ToolContext(mock=False, env={}),
    )
    assert result.ok is True
    assert result.data["provider"] == "yt_dlp"


def test_mock_crawler_discovers_requested_number() -> None:
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "heated cup", "limit": 3},
        ToolContext(mock=True),
    )
    assert result.ok is True
    assert len(result.data["items"]) == 3
    assert all("tiktok.com" in item["url"] for item in result.data["items"])


def test_crawler_returns_specific_chinese_target_validation() -> None:
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "", "limit": 1},
        ToolContext(mock=False, env={}),
    )
    assert result.ok is False
    assert result.error == {"category": "validation", "message": "请输入关键词"}


def test_trending_does_not_require_target() -> None:
    result = tiktok_crawler.execute(
        {"target_type": "trending", "target": "", "limit": 1},
        ToolContext(mock=True, env={}),
    )
    assert result.ok is True


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
    project = client.get(f"/api/v2/pipeline/{payload['results'][0]['project_id']}").json()
    collector = next(node for node in project["nodes"] if node["agent"] == "collector")
    assert collector["status"] == "succeeded"

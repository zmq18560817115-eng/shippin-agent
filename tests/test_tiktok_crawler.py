import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from orchestrator import api, queue
from orchestrator.api import app
from tools.base_tool import ToolContext
from tools.collect import tiktok_crawler
from tools.collect import tiktok_api_adapter
from tools.collect import tiktok_browser_search


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


def test_auto_provider_prefers_authenticated_browser_search(monkeypatch, tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n" + "x" * 200, encoding="ascii")
    monkeypatch.setattr(tiktok_browser_search, "package_available", lambda: True)
    monkeypatch.setattr(
        tiktok_browser_search,
        "discover",
        lambda **kwargs: [
            {
                "url": "https://www.tiktok.com/@brand/video/99",
                "caption": "bottle warmer for night feeds",
                "title": "bottle warmer for night feeds",
            }
        ],
    )
    monkeypatch.setattr(tiktok_crawler, "_enrich_browser_candidates", lambda items, limit, env: items)

    result = tiktok_crawler.execute(
        {"target_type": "keyword", "target": "bottle warmer", "limit": 1, "expand_queries": False},
        ToolContext(mock=False, env={"TIKTOK_COOKIES_FILE": str(cookie_file)}),
    )

    assert result.ok is True
    assert result.data["provider"] == "browser_search"
    assert result.data["items"][0]["relevance"]["relevant"] is True


def test_browser_search_uses_recent_cache_after_temporary_empty_page(monkeypatch, tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n" + "x" * 200, encoding="ascii")
    cache_file = tmp_path / "search-cache.json"
    env = {
        "TIKTOK_COOKIES_FILE": str(cookie_file),
        "TIKTOK_SEARCH_CACHE_PATH": str(cache_file),
        "TIKTOK_BROWSER_SEARCH_RETRIES": "1",
    }
    cached_item = {"url": "https://www.tiktok.com/@brand/video/88", "title": "bottle warmer review"}
    tiktok_browser_search._store_cache("keyword", "bottle warmer", [cached_item], env)
    monkeypatch.setattr(tiktok_browser_search, "package_available", lambda: True)
    monkeypatch.setattr(
        tiktok_browser_search.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout='{"ok":true,"items":[]}\n', stderr=""),
    )

    items = tiktok_browser_search.discover(
        target_type="keyword", target="bottle warmer", limit=3, env=env
    )

    assert items[0]["title"] == "bottle warmer review"
    assert items[0]["discovery_source"] == "cached_browser_search"


def test_browser_candidates_are_enriched_with_real_metadata(monkeypatch) -> None:
    monkeypatch.setattr(tiktok_crawler.shutil, "which", lambda name: "yt-dlp" if name == "yt-dlp" else None)
    monkeypatch.setattr(
        tiktok_crawler,
        "_video_metadata",
        lambda url, env: {
            "url": "https://www.tiktok.com/@canonical-brand/video/1",
            "title": "Portable bottle warmer for night feeds",
            "caption": "Portable bottle warmer for night feeds",
            "play_count": 120000,
        },
    )
    items = [{"url": "https://www.tiktok.com/@brand/video/1", "title": "Top", "discovery_query": "bottle warmer"}]

    enriched = tiktok_crawler._enrich_browser_candidates(items, 1, {})

    assert enriched[0]["title"] == "Portable bottle warmer for night feeds"
    assert enriched[0]["url"] == "https://www.tiktok.com/@canonical-brand/video/1"
    assert enriched[0]["play_count"] == 120000
    assert enriched[0]["discovery_query"] == "bottle warmer"


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


def test_netscape_cookie_file_is_converted_to_tiktok_api_session_mapping(tmp_path: Path) -> None:
    cookie_file = tmp_path / "cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".tiktok.com\tTRUE\t/\tTRUE\t1999999999\tmsToken\ttoken-value\n"
        "#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t1999999999\tsessionid\tsession-value\n",
        encoding="ascii",
    )

    cookies = tiktok_api_adapter._load_netscape_cookies(str(cookie_file))

    assert cookies == {"msToken": "token-value", "sessionid": "session-value"}
    assert all(isinstance(value, str) for value in cookies.values())


def test_keyword_discovery_expands_queries_and_deduplicates(monkeypatch) -> None:
    calls: list[str] = []

    def discover(**kwargs):
        calls.append(kwargs["target"])
        return [
            {
                "url": "https://www.tiktok.com/@brand/video/42",
                "caption": "portable bottle warmer",
                "play_count": 20000,
            }
        ]

    monkeypatch.setattr(tiktok_api_adapter, "discover", discover)
    result = tiktok_crawler.execute(
        {"target_type": "keyword", "provider": "tiktok_api", "target": "便携恒温杯", "limit": 3},
        ToolContext(mock=False, env={"TIKTOK_MS_TOKEN": "secret"}),
    )

    assert result.ok is True
    assert len(result.data["items"]) == 1
    assert calls[0] == "便携恒温杯"
    assert "portable bottle warmer" in calls


def test_tiktok_api_worker_empty_output_becomes_actionable_error(monkeypatch) -> None:
    monkeypatch.setattr(tiktok_api_adapter, "package_available", lambda: True)
    monkeypatch.setattr(
        tiktok_api_adapter.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="", stderr=""),
    )

    try:
        tiktok_api_adapter.discover(
            target_type="keyword",
            target="portable bottle warmer",
            limit=3,
            env={"TIKTOK_MS_TOKEN": "secret"},
        )
    except RuntimeError as exc:
        assert "未返回数据" in str(exc)
    else:
        raise AssertionError("empty worker output must fail")


def test_auto_account_falls_back_to_ytdlp_when_tiktok_api_fails(monkeypatch) -> None:
    monkeypatch.setattr(tiktok_api_adapter, "configured", lambda env: True)
    monkeypatch.setattr(tiktok_api_adapter, "discover", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("blocked")))
    monkeypatch.setattr(tiktok_crawler.shutil, "which", lambda name: "yt-dlp.exe")
    monkeypatch.setattr(
        tiktok_crawler,
        "_discover_account",
        lambda url, limit, env=None: [{"url": "https://www.tiktok.com/@brand/video/99"}],
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
        lambda url, limit, env=None: [{"url": "https://www.tiktok.com/@brand/video/100"}],
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
    material = client.get(f"/api/v2/collect/materials/{payload['results'][0]['material_id']}").json()
    analysis = json.loads(material["ai_analysis_json"])["analysis"]
    assert material["video_title"].startswith("Mock crawler result")
    assert analysis["hook_3s"]
    project = client.get(f"/api/v2/pipeline/{payload['results'][0]['project_id']}").json()
    collector = next(node for node in project["nodes"] if node["agent"] == "collector")
    assert collector["status"] == "succeeded"


def test_auto_collector_can_be_configured_and_run_on_demand(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "auto.db"))
    monkeypatch.setenv("VAF_RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("VAF_MATERIAL_LIBRARY_ROOT", str(tmp_path / "materials"))
    with TestClient(app) as client:
        saved = client.put(
            "/api/v2/collect/tiktok/auto",
            json={
                "enabled": True,
                "target_type": "keyword",
                "provider": "auto",
                "target": "heated cup",
                "limit": 2,
                "interval_minutes": 30,
                "product_id": "便携恒温杯",
                "mock": True,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["enabled"] is True
        assert saved.json()["target"] == "heated cup"

        ran = client.post("/api/v2/collect/tiktok/auto/run-now")
        assert ran.status_code == 200, ran.text
        assert ran.json()["ran"] is True
        assert ran.json()["result"]["completed_count"] == 2
        assert ran.json()["settings"]["last_finished_at"]


def test_auto_collector_env_real_flag_enables_real_collection(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("VAF_DB_PATH", str(tmp_path / "auto-real.db"))
    monkeypatch.setenv("VAF_AUTO_COLLECT_ENABLED", "true")
    monkeypatch.setenv("VAF_AUTO_COLLECT_TARGET", "heated cup")
    monkeypatch.setenv("VAF_AUTO_COLLECT_REAL", "true")
    api._ensure_auto_collector_settings()
    assert api._auto_collector_settings()["mock"] is False


def test_auto_collector_recovers_abandoned_run_and_retries_with_backoff(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "auto-recovery.db"
    monkeypatch.setenv("VAF_DB_PATH", str(db_path))
    api._ensure_auto_collector_settings()
    api._save_auto_collector_settings(
        api.AutoCollectorSettingsRequest(
            enabled=True,
            target_type="keyword",
            provider="auto",
            target="heated cup",
            limit=1,
            interval_minutes=10,
            product_id="便携恒温杯",
            mock=True,
        )
    )
    with queue.get_conn(db_path) as conn:
        conn.execute("UPDATE collector_schedules SET status = 'running', failure_count = 2 WHERE id = 1")

    api._recover_auto_collector_on_startup()
    recovered = api._auto_collector_settings()
    assert recovered["status"] == "failed"
    assert recovered["failure_count"] == 3
    assert recovered["next_run_at"]
    assert api._auto_collector_due(recovered) is False

    monkeypatch.setattr(api, "crawl_tiktok_and_run", lambda request: (_ for _ in ()).throw(RuntimeError("provider blocked")))
    failed = api._run_auto_collector_once(force=True)
    assert failed["ok"] is False
    assert failed["settings"]["failure_count"] == 4
    assert failed["settings"]["next_run_at"]

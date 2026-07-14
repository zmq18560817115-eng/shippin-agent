from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

import httpx

from tools.base_tool import ToolContext, ToolResult
from tools.tool_registry import register_tool


APIFY_ENDPOINT = "https://api.apify.com/v2/acts/clockworks~tiktok-scraper/run-sync-get-dataset-items"


@register_tool("tiktok_crawler")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    target_type = str(payload.get("target_type") or "keyword").strip().casefold()
    target = str(payload.get("target") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 3), 10))
    if target_type not in {"keyword", "account"}:
        return ToolResult.failure("validation", "target_type must be keyword or account")
    if not target:
        return ToolResult.failure("validation", "a keyword or TikTok account URL is required")
    if context.mock:
        return ToolResult.success(
            {"provider": "mock", "target_type": target_type, "target": target, "items": _mock_items(target, limit)},
            meta={"tool": "tiktok_crawler", "mock": True},
        )
    if target_type == "keyword":
        token = str(context.env.get("APIFY_API_TOKEN") or "").strip()
        if not token:
            return ToolResult.failure("not_configured", "关键词爬取需要在 .env.local 配置 APIFY_API_TOKEN")
        try:
            items = _discover_keyword(target, limit, token)
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult.failure("provider", f"TikTok keyword discovery failed: {exc}")
        provider = "apify"
    else:
        if not _is_account_url(target):
            return ToolResult.failure("validation", "account target must be a TikTok profile URL")
        try:
            items = _discover_account(target, limit)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            return ToolResult.failure("provider", f"TikTok account discovery failed: {exc}")
        provider = "yt-dlp"
    if not items:
        return ToolResult.failure("provider", "TikTok crawler returned no videos")
    return ToolResult.success(
        {"provider": provider, "target_type": target_type, "target": target, "items": items[:limit]},
        meta={"tool": "tiktok_crawler", "mock": False, "count": len(items[:limit])},
    )


def _discover_keyword(keyword: str, limit: int, token: str) -> list[dict[str, Any]]:
    response = httpx.post(
        APIFY_ENDPOINT,
        params={"timeout": 180, "limit": limit, "clean": 1, "maxItems": limit},
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "searchQueries": [keyword],
            "resultsPerPage": limit,
            "shouldDownloadVideos": False,
            "shouldDownloadCovers": False,
            "commentsPerPost": 0,
        },
        timeout=200,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("provider returned an unexpected response")
    return _normalize_items(payload)


def _discover_account(url: str, limit: int) -> list[dict[str, Any]]:
    executable = shutil.which("yt-dlp")
    if not executable:
        raise RuntimeError("yt-dlp is not installed or not on PATH")
    completed = subprocess.run(
        [executable, "--flat-playlist", "--playlist-end", str(limit), "--dump-json", url],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        detail = [line for line in completed.stderr.splitlines() if line.strip()]
        raise RuntimeError((detail[-1] if detail else "yt-dlp returned an error")[:500])
    raw = [json.loads(line) for line in completed.stdout.splitlines() if line.strip().startswith("{")]
    return _normalize_items(raw)


def _normalize_items(raw_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_items:
        video_id = str(raw.get("id") or raw.get("videoId") or raw.get("aweme_id") or "").strip()
        url = str(
            raw.get("webpage_url")
            or raw.get("webVideoUrl")
            or raw.get("postPage")
            or raw.get("url")
            or ""
        ).strip()
        if video_id and (not url or "tiktok.com" not in url):
            author = str(raw.get("authorMeta", {}).get("name") if isinstance(raw.get("authorMeta"), dict) else "")
            url = f"https://www.tiktok.com/@{author or 'video'}/video/{video_id}"
        if not url or "tiktok.com" not in url or url in seen:
            continue
        seen.add(url)
        items.append(
            {
                "url": url,
                "caption": str(raw.get("text") or raw.get("description") or raw.get("title") or ""),
                "author_name": str(raw.get("uploader") or raw.get("channel") or ""),
                "like_count": raw.get("diggCount") or raw.get("like_count") or 0,
                "comment_count": raw.get("commentCount") or raw.get("comment_count") or 0,
                "share_count": raw.get("shareCount") or raw.get("repost_count") or 0,
            }
        )
    return items


def _is_account_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").endswith("tiktok.com") and "/@" in parsed.path


def _mock_items(target: str, limit: int) -> list[dict[str, Any]]:
    base = abs(hash(target)) % 10_000_000
    return [
        {
            "url": f"https://www.tiktok.com/@crawler-demo/video/{base + index + 1}",
            "caption": f"Controlled crawler result {index + 1} for {target}",
            "author_name": "crawler-demo",
        }
        for index in range(limit)
    ]

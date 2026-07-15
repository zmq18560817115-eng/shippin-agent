from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any
from urllib.parse import urlparse

import httpx

from tools.base_tool import ToolContext, ToolResult
from tools.collect import tiktok_api_adapter
from tools.tool_registry import register_tool


APIFY_ENDPOINT = "https://api.apify.com/v2/acts/clockworks~tiktok-scraper/run-sync-get-dataset-items"


@register_tool("tiktok_crawler")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    target_type = str(payload.get("target_type") or "keyword").strip().casefold()
    requested_provider = str(payload.get("provider") or "auto").strip().casefold()
    target = str(payload.get("target") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 3), 10))
    if target_type not in {"keyword", "account", "hashtag", "trending"}:
        return ToolResult.failure("validation", "target_type must be keyword, account, hashtag or trending")
    if requested_provider not in {"auto", "tiktok_api", "apify", "yt_dlp"}:
        return ToolResult.failure("validation", "provider must be auto, tiktok_api, apify or yt_dlp")
    if not target and target_type != "trending":
        return ToolResult.failure("validation", "a keyword or TikTok account URL is required")
    if context.mock:
        return ToolResult.success(
            {"provider": "mock", "target_type": target_type, "target": target, "items": _mock_items(target or "trending", limit)},
            meta={"tool": "tiktok_crawler", "mock": True},
        )
    try:
        provider = _select_provider(requested_provider, target_type, context)
    except RuntimeError as exc:
        return ToolResult.failure("not_configured", str(exc))
    if provider == "apify":
        if target_type != "keyword":
            return ToolResult.failure("validation", "Apify provider currently supports keyword targets only")
        token = str(context.env.get("APIFY_API_TOKEN") or "").strip()
        if not token:
            return ToolResult.failure("not_configured", "Apify 关键词采集需要在 .env.local 配置 APIFY_API_TOKEN")
        try:
            items = _discover_keyword(target, limit, token)
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult.failure("provider", f"TikTok keyword discovery failed: {exc}")
        provider = "apify"
    elif provider == "yt_dlp":
        if target_type != "account":
            return ToolResult.failure("validation", "yt-dlp provider currently supports account targets only")
        if not _is_account_url(target):
            return ToolResult.failure("validation", "account target must be a TikTok profile URL")
        try:
            items = _discover_account(target, limit)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            return ToolResult.failure("provider", f"TikTok account discovery failed: {exc}")
        provider = "yt_dlp"
    else:
        try:
            items = tiktok_api_adapter.discover(
                target_type=target_type,
                target=target,
                limit=limit,
                env=context.env,
            )
        except (RuntimeError, ValueError) as exc:
            fallback = _fallback_account_discovery(requested_provider, target_type, target, limit)
            if fallback is not None:
                items, provider = fallback
            else:
                category = "not_configured" if "未配置" in str(exc) or "未安装" in str(exc) else "provider"
                return ToolResult.failure(category, f"TikTokApi 采集失败：{exc}")
        except Exception as exc:
            fallback = _fallback_account_discovery(requested_provider, target_type, target, limit)
            if fallback is not None:
                items, provider = fallback
            else:
                return ToolResult.failure(
                    "provider",
                    f"TikTokApi 采集失败：{exc.__class__.__name__}: {exc}. 请检查 msToken、网络或代理配置",
                )
        else:
            provider = "tiktok_api"
        if not items:
            fallback = _fallback_account_discovery(requested_provider, target_type, target, limit)
            if fallback is not None:
                items, provider = fallback
    if not items:
        return ToolResult.failure("provider", "TikTok crawler returned no videos")
    return ToolResult.success(
        {"provider": provider, "target_type": target_type, "target": target, "items": items[:limit]},
        meta={"tool": "tiktok_crawler", "mock": False, "count": len(items[:limit])},
    )


def _select_provider(requested: str, target_type: str, context: ToolContext) -> str:
    if requested != "auto":
        return requested
    if target_type == "keyword" and str(context.env.get("APIFY_API_TOKEN") or "").strip():
        return "apify"
    if tiktok_api_adapter.configured(context.env):
        return "tiktok_api"
    if target_type == "account" and shutil.which("yt-dlp"):
        return "yt_dlp"
    if target_type == "keyword":
        raise RuntimeError(
            "关键词采集尚未配置：可设置 APIFY_API_TOKEN，或安装 TikTokApi 并设置 TIKTOK_MS_TOKEN（按话题采集）"
        )
    raise RuntimeError("自建采集尚未配置：请安装 TikTokApi 并设置 TIKTOK_MS_TOKEN")


def _fallback_account_discovery(
    requested_provider: str,
    target_type: str,
    target: str,
    limit: int,
) -> tuple[list[dict[str, Any]], str] | None:
    if requested_provider != "auto" or target_type != "account" or not _is_account_url(target):
        return None
    if not shutil.which("yt-dlp"):
        return None
    try:
        return _discover_account(target, limit), "yt_dlp_fallback"
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


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

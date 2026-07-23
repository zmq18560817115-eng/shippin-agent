from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urlparse

import httpx

from tools.base_tool import ToolContext, ToolResult
from tools.collect import relevance, tiktok_api_adapter, tiktok_browser_search
from tools.tool_registry import register_tool


APIFY_ENDPOINT = "https://api.apify.com/v2/acts/clockworks~tiktok-scraper/run-sync-get-dataset-items"


@register_tool("tiktok_crawler")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    target_type = str(payload.get("target_type") or "keyword").strip().casefold()
    requested_provider = str(payload.get("provider") or "auto").strip().casefold()
    target = str(payload.get("target") or "").strip()
    limit = max(1, min(int(payload.get("limit") or 6), 100))
    if target_type not in {"keyword", "account", "hashtag", "trending"}:
        return ToolResult.failure("validation", "发现方式必须是关键词、账号、话题或热门视频")
    if requested_provider not in {"auto", "browser_search", "tiktok_api", "apify", "yt_dlp"}:
        return ToolResult.failure("validation", "请选择有效的采集后端")
    if not target and target_type != "trending":
        names = {"keyword": "关键词", "account": "TikTok 账号主页", "hashtag": "话题标签"}
        return ToolResult.failure("validation", f"请输入{names.get(target_type, '采集目标')}")
    if context.mock:
        return ToolResult.success(
            {"provider": "mock", "target_type": target_type, "target": target, "items": _mock_items(target or "trending", limit)},
            meta={"tool": "tiktok_crawler", "mock": True},
        )
    try:
        provider = _select_provider(requested_provider, target_type, context)
    except RuntimeError as exc:
        return ToolResult.failure("not_configured", str(exc))
    if provider == "browser_search":
        if target_type not in {"keyword", "hashtag"}:
            return ToolResult.failure("validation", "浏览器搜索后端仅支持关键词和话题采集")
        queries = relevance.query_plan(target, target_type=target_type, limit=6) if payload.get("expand_queries", True) else [target]
        try:
            items = _discover_browser_search_queries(target_type, queries, limit, context.env)
        except (RuntimeError, ValueError) as exc:
            if requested_provider == "auto" and str(context.env.get("APIFY_API_TOKEN") or "").strip():
                try:
                    items = _discover_keyword_queries(queries, limit, str(context.env.get("APIFY_API_TOKEN") or "").strip())
                    provider = "apify_fallback"
                except (httpx.HTTPError, ValueError) as fallback_exc:
                    return ToolResult.failure("provider", f"浏览器搜索失败：{exc}；Apify 降级失败：{fallback_exc}")
            elif requested_provider == "auto" and tiktok_api_adapter.configured(context.env):
                try:
                    items = _discover_tiktok_api_queries(target_type, queries, limit, context.env)
                    provider = "tiktok_api_fallback"
                except (RuntimeError, ValueError) as fallback_exc:
                    return ToolResult.failure("provider", f"浏览器搜索失败：{exc}；TikTokApi 降级失败：{fallback_exc}")
            else:
                return ToolResult.failure("provider", f"TikTok 浏览器搜索失败：{exc}")
        else:
            provider = "browser_search"
        items = _enrich_browser_candidates(items, limit, context.env)
    elif provider == "apify":
        if target_type != "keyword":
            return ToolResult.failure("validation", "Apify provider currently supports keyword targets only")
        token = str(context.env.get("APIFY_API_TOKEN") or "").strip()
        if not token:
            return ToolResult.failure("not_configured", "Apify 关键词采集需要在 .env.local 配置 APIFY_API_TOKEN")
        try:
            queries = relevance.query_plan(target, target_type=target_type, limit=6) if payload.get("expand_queries", True) else [target]
            items = _discover_keyword_queries(queries, limit, token)
        except (httpx.HTTPError, ValueError) as exc:
            return ToolResult.failure("provider", f"TikTok keyword discovery failed: {exc}")
        provider = "apify"
    elif provider == "yt_dlp":
        if target_type != "account":
            return ToolResult.failure("validation", "yt-dlp provider currently supports account targets only")
        if not _is_account_url(target):
            return ToolResult.failure("validation", "account target must be a TikTok profile URL")
        try:
            items = _discover_account(target, limit, context.env)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            return ToolResult.failure("provider", f"TikTok account discovery failed: {exc}")
        provider = "yt_dlp"
    else:
        try:
            queries = relevance.query_plan(target, target_type=target_type, limit=6) if payload.get("expand_queries", True) else [target]
            items = _discover_tiktok_api_queries(target_type, queries, limit, context.env)
        except (RuntimeError, ValueError) as exc:
            fallback = _fallback_account_discovery(requested_provider, target_type, target, limit, context.env)
            if fallback is not None:
                items, provider = fallback
            else:
                category = "not_configured" if "未配置" in str(exc) or "未安装" in str(exc) else "provider"
                return ToolResult.failure(category, f"TikTokApi 采集失败：{exc}")
        except Exception as exc:
            fallback = _fallback_account_discovery(requested_provider, target_type, target, limit, context.env)
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
            fallback = _fallback_account_discovery(requested_provider, target_type, target, limit, context.env)
            if fallback is not None:
                items, provider = fallback
    if not items:
        return ToolResult.failure("provider", "TikTok crawler returned no videos")
    if target_type in {"keyword", "hashtag"}:
        ranked: list[dict[str, Any]] = []
        for item in items:
            scored = relevance.score_item(item, target, target_type=target_type)
            quality = relevance.quality_score(item, scored)
            ranked.append({**item, "relevance": scored, "quality": quality})
        ranked.sort(
            key=lambda item: (
                bool((item.get("relevance") or {}).get("relevant")),
                float((item.get("quality") or {}).get("score") or 0),
                int((item.get("quality") or {}).get("play_count") or 0),
            ),
            reverse=True,
        )
        items = ranked
    return ToolResult.success(
        {"provider": provider, "target_type": target_type, "target": target, "items": items[:limit]},
        meta={"tool": "tiktok_crawler", "mock": False, "count": len(items[:limit])},
    )


def _select_provider(requested: str, target_type: str, context: ToolContext) -> str:
    if requested != "auto":
        return requested
    if target_type in {"keyword", "hashtag"} and tiktok_browser_search.configured(context.env):
        return "browser_search"
    if target_type == "keyword" and str(context.env.get("APIFY_API_TOKEN") or "").strip():
        return "apify"
    if tiktok_api_adapter.configured(context.env):
        return "tiktok_api"
    if target_type == "account" and shutil.which("yt-dlp"):
        return "yt_dlp"
    if target_type == "keyword":
        raise RuntimeError(
            "关键词采集尚未配置：请配置有效 TikTok Cookies，或设置 APIFY_API_TOKEN/TIKTOK_MS_TOKEN"
        )
    raise RuntimeError("自建采集尚未配置：请安装 TikTokApi 并设置 TIKTOK_MS_TOKEN")


def _fallback_account_discovery(
    requested_provider: str,
    target_type: str,
    target: str,
    limit: int,
    env: Mapping[str, str],
) -> tuple[list[dict[str, Any]], str] | None:
    if requested_provider != "auto" or target_type != "account" or not _is_account_url(target):
        return None
    if not shutil.which("yt-dlp"):
        return None
    try:
        return _discover_account(target, limit, env), "yt_dlp_fallback"
    except (RuntimeError, subprocess.TimeoutExpired):
        return None


def _discover_tiktok_api_queries(
    target_type: str,
    queries: list[str],
    limit: int,
    env: Mapping[str, str],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    per_query = min(100, max(limit, 12))
    for query in queries:
        try:
            discovered = tiktok_api_adapter.discover(
                target_type=target_type,
                target=query,
                limit=per_query,
                env=env,
            )
        except (RuntimeError, ValueError) as exc:
            errors.append(f"{query}: {exc}")
            continue
        for item in discovered:
            candidate = dict(item)
            candidate["discovery_query"] = query
            merged.append(candidate)
    output = _deduplicate(merged)
    if not output and errors:
        raise RuntimeError("；".join(errors[:3]))
    return output[: max(limit * 4, limit)]


def _discover_browser_search_queries(
    target_type: str,
    queries: list[str],
    limit: int,
    env: Mapping[str, str],
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    errors: list[str] = []
    per_query = min(100, max(limit * 2, 12))
    for query in queries:
        try:
            discovered = tiktok_browser_search.discover(
                target_type=target_type,
                target=query,
                limit=per_query,
                env=env,
            )
        except (RuntimeError, ValueError) as exc:
            errors.append(f"{query}: {exc}")
            continue
        for item in discovered:
            candidate = dict(item)
            candidate["discovery_query"] = query
            merged.append(candidate)
        if len(_deduplicate(merged)) >= max(limit * 3, limit):
            break
    output = _deduplicate(merged)
    if not output and errors:
        raise RuntimeError("；".join(errors[:3]))
    return output[: max(limit * 4, limit)]


def _enrich_browser_candidates(
    items: list[dict[str, Any]],
    limit: int,
    env: Mapping[str, str],
) -> list[dict[str, Any]]:
    if not shutil.which("yt-dlp") or not items:
        return items
    try:
        enrich_limit = max(1, min(int(env.get("VAF_TIKTOK_ENRICH_LIMIT") or min(max(limit, 4), 8)), 30))
    except (TypeError, ValueError):
        enrich_limit = min(max(limit, 4), 8)
    selected = items[:enrich_limit]
    enriched_by_url: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(4, len(selected))) as pool:
        futures = {pool.submit(_video_metadata, str(item.get("url") or ""), env): item for item in selected}
        for future in as_completed(futures):
            source_item = futures[future]
            try:
                metadata = future.result()
            except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
                continue
            if metadata:
                # yt-dlp may canonicalize the account slug or URL. Preserve the
                # discovery URL as the join key so real title/stats replace
                # generic TikTok page chrome text reliably.
                enriched_by_url[str(source_item.get("url") or "")] = metadata
    output: list[dict[str, Any]] = []
    for item in items:
        url = str(item.get("url") or "")
        metadata = enriched_by_url.get(url)
        output.append({**item, **metadata, "discovery_query": item.get("discovery_query")} if metadata else item)
    return output


def _video_metadata(url: str, env: Mapping[str, str]) -> dict[str, Any] | None:
    if not url:
        return None
    executable = shutil.which("yt-dlp")
    if not executable:
        return None
    command = [executable, "--skip-download", "--dump-single-json", "--no-warnings"]
    command.extend(_yt_dlp_auth_args(env))
    command.append(url)
    try:
        timeout_s = max(5, min(int(env.get("VAF_TIKTOK_METADATA_TIMEOUT_S") or 15), 60))
    except (TypeError, ValueError):
        timeout_s = 15
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        timeout=timeout_s,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        raise RuntimeError("yt-dlp metadata lookup failed")
    raw = json.loads(completed.stdout)
    normalized = _normalize_items([raw])
    return normalized[0] if normalized else None


def _discover_keyword_queries(queries: list[str], limit: int, token: str) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for query in queries:
        for item in _discover_keyword(query, min(100, max(limit, 12)), token):
            candidate = dict(item)
            candidate["discovery_query"] = query
            merged.append(candidate)
    return _deduplicate(merged)[: max(limit * 4, limit)]


def _deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        url = str(item.get("url") or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        output.append(item)
    return output


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


def _discover_account(url: str, limit: int, env: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    executable = shutil.which("yt-dlp")
    if not executable:
        raise RuntimeError("yt-dlp is not installed or not on PATH")
    command = [executable, "--flat-playlist", "--playlist-end", str(limit), "--dump-json"]
    command.extend(_yt_dlp_auth_args(env or {}))
    command.append(url)
    completed = subprocess.run(
        command,
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


def _yt_dlp_auth_args(env: Mapping[str, str]) -> list[str]:
    cookies_file = str(env.get("TIKTOK_COOKIES_FILE") or "").strip()
    if cookies_file:
        return ["--cookies", cookies_file]
    cookies_browser = str(env.get("TIKTOK_COOKIES_BROWSER") or "").strip()
    if cookies_browser:
        return ["--cookies-from-browser", cookies_browser]
    return []


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
        author_meta = raw.get("authorMeta") if isinstance(raw.get("authorMeta"), dict) else {}
        hashtags_raw = raw.get("hashtags") if isinstance(raw.get("hashtags"), list) else []
        hashtags = [
            str(value.get("name") or value.get("title") or "").strip() if isinstance(value, dict) else str(value).strip("# ")
            for value in hashtags_raw
        ]
        items.append(
            {
                "url": url,
                "title": str(raw.get("title") or raw.get("text") or raw.get("description") or ""),
                "caption": str(raw.get("text") or raw.get("description") or raw.get("title") or ""),
                "author_name": str(raw.get("uploader") or raw.get("channel") or author_meta.get("name") or ""),
                "author_url": str(raw.get("uploader_url") or raw.get("channel_url") or author_meta.get("profileUrl") or ""),
                "cover_url": str(raw.get("thumbnail") or raw.get("thumbnail_url") or raw.get("cover") or ""),
                "hashtags": [value for value in hashtags if value],
                "like_count": raw.get("diggCount") or raw.get("like_count") or 0,
                "comment_count": raw.get("commentCount") or raw.get("comment_count") or 0,
                "share_count": raw.get("shareCount") or raw.get("repost_count") or 0,
                "collect_count": raw.get("collectCount") or raw.get("collect_count") or 0,
                "play_count": raw.get("playCount") or raw.get("view_count") or 0,
                "publish_time": raw.get("createTime") or raw.get("timestamp"),
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
            "title": f"Mock crawler result {index + 1}",
            "caption": f"Controlled crawler result {index + 1} for {target}",
            "author_name": "crawler-demo",
        }
        for index in range(limit)
    ]

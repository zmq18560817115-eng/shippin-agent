from __future__ import annotations

import asyncio
import importlib.util
import re
from typing import Any, Mapping
from urllib.parse import urlparse


def package_available() -> bool:
    return importlib.util.find_spec("TikTokApi") is not None


def configured(env: Mapping[str, str]) -> bool:
    return package_available() and bool(str(env.get("TIKTOK_MS_TOKEN") or "").strip())


def discover(
    *,
    target_type: str,
    target: str,
    limit: int,
    env: Mapping[str, str],
) -> list[dict[str, Any]]:
    if not package_available():
        raise RuntimeError("TikTokApi 未安装，请运行 pip install -r requirements-tiktok.txt")
    token = str(env.get("TIKTOK_MS_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("未配置 TIKTOK_MS_TOKEN，请按 docs/TikTokApi接入说明.md 写入 .env.local")
    return asyncio.run(_discover(target_type=target_type, target=target, limit=limit, env=env, token=token))


async def _discover(
    *,
    target_type: str,
    target: str,
    limit: int,
    env: Mapping[str, str],
    token: str,
) -> list[dict[str, Any]]:
    from TikTokApi import TikTokApi

    browser = str(env.get("TIKTOK_BROWSER") or "chromium").strip().casefold()
    if browser not in {"chromium", "firefox", "webkit"}:
        raise ValueError("TIKTOK_BROWSER 必须是 chromium、firefox 或 webkit")
    proxy = str(env.get("TIKTOK_PROXY") or "").strip()
    proxies = [{"server": proxy}] if proxy else None
    timeout_ms = max(10_000, int(env.get("TIKTOK_TIMEOUT_MS") or 45_000))

    async with TikTokApi() as api:
        await api.create_sessions(
            num_sessions=1,
            ms_tokens=[token],
            proxies=proxies,
            sleep_after=2,
            browser=browser,
            timeout=timeout_ms,
        )
        if target_type == "account":
            username = _username_from_target(target)
            source = api.user(username=username).videos(count=limit)
        elif target_type in {"keyword", "hashtag"}:
            hashtag = _hashtag_from_target(target)
            source = api.hashtag(name=hashtag).videos(count=limit)
        elif target_type == "trending":
            source = api.trending.videos(count=limit)
        else:
            raise ValueError("TikTokApi 仅支持 account、hashtag/keyword 或 trending")

        items: list[dict[str, Any]] = []
        async for video in source:
            item = _normalize_video(getattr(video, "as_dict", {}) or {})
            if item:
                items.append(item)
            if len(items) >= limit:
                break
        return items


def _username_from_target(value: str) -> str:
    value = value.strip()
    if value.startswith("@"):
        return value[1:]
    parsed = urlparse(value)
    match = re.search(r"/@([^/?]+)", parsed.path)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9._]+", value):
        return value
    raise ValueError("账号请输入 @用户名、用户名或 TikTok 账号主页 URL")


def _hashtag_from_target(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    match = re.search(r"/tag/([^/?]+)", parsed.path)
    if match:
        value = match.group(1)
    value = value.lstrip("#").strip().replace(" ", "")
    if not value:
        raise ValueError("话题不能为空")
    return value


def _normalize_video(raw: dict[str, Any]) -> dict[str, Any] | None:
    video_id = str(raw.get("id") or "").strip()
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    username = str(author.get("uniqueId") or author.get("unique_id") or "").strip()
    if not video_id:
        return None
    url = f"https://www.tiktok.com/@{username or 'video'}/video/{video_id}"
    stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
    return {
        "url": url,
        "caption": str(raw.get("desc") or raw.get("text") or ""),
        "author_name": username,
        "like_count": stats.get("diggCount") or 0,
        "comment_count": stats.get("commentCount") or 0,
        "share_count": stats.get("shareCount") or 0,
        "play_count": stats.get("playCount") or 0,
    }

from __future__ import annotations

import asyncio
import http.cookiejar
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


def package_available() -> bool:
    return importlib.util.find_spec("TikTokApi") is not None


def configured(env: Mapping[str, str]) -> bool:
    token = bool(str(env.get("TIKTOK_MS_TOKEN") or "").strip())
    cookies_file = str(env.get("TIKTOK_COOKIES_FILE") or "").strip()
    return package_available() and (token or bool(cookies_file))


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
    cookies_file = str(env.get("TIKTOK_COOKIES_FILE") or "").strip()
    if not token and not cookies_file:
        raise RuntimeError("未配置 TikTok 会话，请在 .env.local 设置 TIKTOK_MS_TOKEN 或 TIKTOK_COOKIES_FILE")
    timeout_sec = max(15, int(env.get("TIKTOK_WORKER_TIMEOUT_SEC") or 75))
    request = {
        "target_type": target_type,
        "target": target,
        "limit": limit,
        "token": token,
        "browser": str(env.get("TIKTOK_BROWSER") or "chromium"),
        "proxy": str(env.get("TIKTOK_PROXY") or ""),
        "timeout_ms": str(env.get("TIKTOK_TIMEOUT_MS") or "45000"),
        "headless": str(env.get("TIKTOK_HEADLESS") or "true"),
        "cookies_file": cookies_file,
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "tools.collect.tiktok_api_worker"],
            input=json.dumps(request, ensure_ascii=False),
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            capture_output=True,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"TikTok 浏览器采集超过 {timeout_sec} 秒，已终止本次任务") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "采集子进程异常退出").strip()
        raise RuntimeError(detail[-800:])
    output = completed.stdout.strip()
    if not output:
        raise RuntimeError("TikTok 浏览器采集未返回数据，可能遇到验证码、地区限制或失效会话")
    try:
        response = json.loads(output.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError("TikTok 浏览器采集返回了无法解析的结果") from exc
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error") or "TikTok 浏览器采集失败"))
    return list(response.get("items") or [])


def discover_direct(
    *,
    target_type: str,
    target: str,
    limit: int,
    env: Mapping[str, str],
    token: str,
) -> list[dict[str, Any]]:
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
    from TikTokApi.stealth import stealth_async

    browser = str(env.get("TIKTOK_BROWSER") or "chromium").strip().casefold()
    if browser not in {"chromium", "firefox", "webkit"}:
        raise ValueError("TIKTOK_BROWSER 必须是 chromium、firefox 或 webkit")
    proxy = str(env.get("TIKTOK_PROXY") or "").strip()
    proxies = [{"server": proxy}] if proxy else None
    timeout_ms = max(10_000, int(env.get("TIKTOK_TIMEOUT_MS") or 45_000))
    headless = str(env.get("TIKTOK_HEADLESS") or "true").strip().casefold() not in {"0", "false", "no", "off"}
    cookies = _load_netscape_cookies(str(env.get("TIKTOK_COOKIES_FILE") or "").strip())
    ms_tokens = [token] if token else None

    async def page_factory(context):
        page = await context.new_page()
        page.set_default_navigation_timeout(timeout_ms)
        await stealth_async(page)
        await page.route(
            "**/*",
            lambda route, request: (
                route.abort()
                if request.resource_type in {"image", "media", "font"}
                else route.continue_()
            ),
        )
        await page.goto(
            "https://www.tiktok.com/",
            wait_until="domcontentloaded",
            timeout=timeout_ms,
        )
        return page

    async with TikTokApi() as api:
        await api.create_sessions(
            num_sessions=1,
            headless=headless,
            ms_tokens=ms_tokens,
            cookies=[cookies] if cookies else None,
            proxies=proxies,
            sleep_after=2,
            browser=browser,
            timeout=timeout_ms,
            suppress_resource_load_types=["image", "media", "font"],
            page_factory=page_factory,
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


def _load_netscape_cookies(path_text: str) -> dict[str, str]:
    if not path_text:
        return []
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise ValueError(f"TikTok Cookie 文件不存在：{path}")
    jar = http.cookiejar.MozillaCookieJar(path.as_posix())
    try:
        jar.load(ignore_discard=True, ignore_expires=True)
    except (OSError, http.cookiejar.LoadError) as exc:
        raise ValueError(f"无法读取 TikTok Cookie 文件：{exc}") from exc
    cookies: dict[str, str] = {}
    for cookie in jar:
        cookies[str(cookie.name)] = str(cookie.value)
    return cookies


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
    video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
    cover = video.get("cover") or video.get("originCover") or video.get("dynamicCover") or ""
    challenges = raw.get("challenges") if isinstance(raw.get("challenges"), list) else []
    hashtags = [
        str(item.get("title") or "").strip()
        for item in challenges
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    ]
    return {
        "url": url,
        "title": str(raw.get("desc") or raw.get("text") or ""),
        "caption": str(raw.get("desc") or raw.get("text") or ""),
        "author_name": username,
        "author_url": f"https://www.tiktok.com/@{username}" if username else "",
        "cover_url": str(cover),
        "hashtags": hashtags,
        "like_count": stats.get("diggCount") or 0,
        "comment_count": stats.get("commentCount") or 0,
        "share_count": stats.get("shareCount") or 0,
        "collect_count": stats.get("collectCount") or 0,
        "play_count": stats.get("playCount") or 0,
        "publish_time": raw.get("createTime"),
    }

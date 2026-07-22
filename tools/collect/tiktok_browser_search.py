from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
_CACHE_LOCK = threading.Lock()


def package_available() -> bool:
    return importlib.util.find_spec("playwright") is not None


def configured(env: Mapping[str, str]) -> bool:
    cookies_file = Path(str(env.get("TIKTOK_COOKIES_FILE") or "").strip()).expanduser()
    return package_available() and cookies_file.is_file() and cookies_file.stat().st_size > 100


def discover(*, target_type: str, target: str, limit: int, env: Mapping[str, str]) -> list[dict[str, Any]]:
    if target_type not in {"keyword", "hashtag"}:
        raise ValueError("浏览器搜索后端仅支持关键词和话题采集")
    if not configured(env):
        raise RuntimeError("浏览器搜索需要 Playwright 和有效的 TIKTOK_COOKIES_FILE")

    timeout_sec = max(30, int(env.get("TIKTOK_BROWSER_SEARCH_TIMEOUT_SEC") or 90))
    retries = max(1, min(int(env.get("TIKTOK_BROWSER_SEARCH_RETRIES") or 3), 5))
    request = {
        "target_type": target_type,
        "target": target,
        "limit": limit,
        "cookies_file": str(env.get("TIKTOK_COOKIES_FILE") or ""),
        "headless": str(env.get("TIKTOK_HEADLESS") or "true"),
        "wait_ms": str(env.get("TIKTOK_SEARCH_WAIT_MS") or "12000"),
        "browser": str(env.get("TIKTOK_BROWSER_SEARCH_BROWSER") or "chromium"),
    }
    last_error = "TikTok 浏览器搜索未返回视频"
    for attempt in range(1, retries + 1):
        try:
            completed = subprocess.run(
                [sys.executable, "-m", "tools.collect.tiktok_browser_search_worker"],
                input=json.dumps(request, ensure_ascii=False),
                text=True,
                encoding="utf-8",
                errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                capture_output=True,
                timeout=timeout_sec,
                check=False,
            )
        except subprocess.TimeoutExpired:
            last_error = f"TikTok 浏览器搜索超过 {timeout_sec} 秒"
        else:
            output = completed.stdout.strip()
            if completed.returncode != 0:
                last_error = (completed.stderr or output or "浏览器搜索子进程异常退出").strip()[-1200:]
            elif not output:
                last_error = "TikTok 浏览器搜索未返回数据"
            else:
                response = json.loads(output.splitlines()[-1])
                if not response.get("ok"):
                    last_error = str(response.get("error") or "TikTok 浏览器搜索失败")
                else:
                    items = list(response.get("items") or [])
                    if items:
                        live_items = [{**item, "discovery_source": "live_browser_search"} for item in items]
                        _store_cache(target_type, target, live_items, env)
                        return live_items
                    last_error = "TikTok 搜索页暂时为空"
        if attempt < retries:
            time.sleep(min(attempt * 2, 5))
    cached = _load_cache(target_type, target, env)
    if cached:
        return [{**item, "discovery_source": "cached_browser_search"} for item in cached]
    raise RuntimeError(f"{last_error}（已尝试 {retries} 次，且没有可用缓存）")


def _cache_path(env: Mapping[str, str]) -> Path:
    configured_path = str(env.get("TIKTOK_SEARCH_CACHE_PATH") or "").strip()
    if configured_path:
        path = Path(configured_path).expanduser()
        return path if path.is_absolute() else ROOT / path
    return ROOT / "data" / "runtime" / "tiktok-search-cache.json"


def _cache_key(target_type: str, target: str) -> str:
    return f"{target_type.strip().casefold()}:{' '.join(target.strip().casefold().split())}"


def _store_cache(target_type: str, target: str, items: list[dict[str, Any]], env: Mapping[str, str]) -> None:
    path = _cache_path(env)
    key = _cache_key(target_type, target)
    with _CACHE_LOCK:
        payload = _read_cache_file(path)
        payload[key] = {"saved_at": time.time(), "items": items}
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(path)


def _load_cache(target_type: str, target: str, env: Mapping[str, str]) -> list[dict[str, Any]]:
    try:
        max_age_seconds = max(60, int(env.get("TIKTOK_SEARCH_CACHE_MAX_AGE_SEC") or 86400))
    except (TypeError, ValueError):
        max_age_seconds = 86400
    with _CACHE_LOCK:
        entry = _read_cache_file(_cache_path(env)).get(_cache_key(target_type, target)) or {}
    if time.time() - float(entry.get("saved_at") or 0) > max_age_seconds:
        return []
    return [dict(item) for item in entry.get("items") or [] if isinstance(item, dict)]


def _read_cache_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}

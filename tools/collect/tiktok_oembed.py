from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

import httpx

from tools.base_tool import ToolContext, ToolResult
from tools.collect import manual_import
from tools.tool_registry import register_tool


OEMBED_URL = "https://www.tiktok.com/oembed"
TIKTOK_HOSTS = {"tiktok.com", "www.tiktok.com", "m.tiktok.com", "vm.tiktok.com", "vt.tiktok.com"}
FetchJson = Callable[[str], dict[str, Any]]


@register_tool("tiktok_oembed")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    try:
        result = collect_links(
            manual_import.extract_items(payload),
            product_id=str(payload.get("product_id") or "便携恒温杯"),
            source_keyword=str(payload.get("source_keyword") or "tiktok_oembed"),
            library_root=payload.get("library_root"),
            timeout_s=float(payload.get("timeout_s") or 20),
            proxy=str(context.env.get("TIKTOK_PROXY") or "").strip() or None,
        )
    except ValueError as exc:
        return ToolResult.failure("validation", str(exc))
    except httpx.HTTPError as exc:
        return ToolResult.failure("provider", f"TikTok oEmbed request failed: {exc}")
    return ToolResult.success(result, meta={"tool": "tiktok_oembed", "count": result["imported_count"]})


def collect_links(
    items: list[dict[str, Any]],
    *,
    product_id: str,
    source_keyword: str,
    library_root: str | None = None,
    timeout_s: float = 20,
    fetch_json: FetchJson | None = None,
    proxy: str | None = None,
) -> dict[str, Any]:
    if not items:
        raise ValueError("at least one TikTok URL is required")

    fetch = fetch_json or _http_fetcher(timeout_s, proxy=proxy)
    enriched: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for item in items:
        url = str(item.get("url") or item.get("source_url") or "").strip()
        if not _is_tiktok_url(url):
            failures.append({"url": url, "error": "unsupported TikTok URL"})
            continue
        try:
            metadata = fetch(url)
        except (ValueError, httpx.HTTPError) as exc:
            failures.append({"url": url, "error": str(exc)})
            continue
        enriched.append(_to_import_item(url, metadata))

    if not enriched:
        detail = failures[0]["error"] if failures else "no metadata returned"
        raise ValueError(f"no TikTok links could be resolved: {detail}")

    imported = manual_import.import_links(
        enriched,
        product_id=product_id,
        source_keyword=source_keyword,
        library_root=library_root,
    )
    imported["provider"] = "tiktok_oembed"
    imported["resolved_count"] = len(enriched)
    imported["failed_count"] = len(failures)
    imported["failures"] = failures
    return imported


def _http_fetcher(timeout_s: float, *, proxy: str | None = None) -> FetchJson:
    def fetch(url: str) -> dict[str, Any]:
        with httpx.Client(timeout=timeout_s, follow_redirects=True, proxy=proxy) as client:
            response = client.get(OEMBED_URL, params={"url": url})
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("title"):
            raise ValueError("TikTok oEmbed returned incomplete metadata")
        return payload

    return fetch


def _to_import_item(url: str, metadata: dict[str, Any]) -> dict[str, Any]:
    caption = str(metadata.get("title") or "")
    return {
        "url": url,
        "video_title": caption,
        "caption": caption,
        "author_name": str(metadata.get("author_name") or ""),
        "author_url": str(metadata.get("author_url") or ""),
        "cover_url": str(metadata.get("thumbnail_url") or ""),
        "hashtags": [tag.lstrip("#") for tag in re.findall(r"#[\w-]+", caption)],
        "processing_status": "needs_review",
        "asset_intake_notes": "Metadata resolved through TikTok oEmbed; engagement metrics and video file were not collected.",
    }


def _is_tiktok_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in TIKTOK_HOSTS

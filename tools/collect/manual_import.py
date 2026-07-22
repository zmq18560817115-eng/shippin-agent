from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from libshared import artifacts
from libshared.paths import DATA_ROOT, ROOT
from tools.base_tool import ToolContext, ToolResult
from tools.tool_registry import register_tool


URL_RE = re.compile(r"https?://[^\s,;，；]+", re.IGNORECASE)
DEFAULT_SOURCE_KEYWORD = "manual_tiktok"
LIBRARY_INDEX_NAME = "library_index.json"


@register_tool("manual_import")
def execute(payload: dict[str, Any], context: ToolContext) -> ToolResult:
    try:
        result = import_links(
            _extract_items(payload),
            product_id=str(payload.get("product_id") or "便携恒温杯"),
            source_keyword=str(payload.get("source_keyword") or DEFAULT_SOURCE_KEYWORD),
            library_root=_resolve_library_root(payload.get("library_root"), context),
        )
    except ValueError as exc:
        return ToolResult.failure("validation", str(exc))
    return ToolResult.success(result, meta={"tool": "manual_import", "count": result["imported_count"]})


def import_links(
    items: list[dict[str, Any]],
    *,
    product_id: str,
    source_keyword: str,
    library_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    if not items:
        raise ValueError("at least one TikTok/link URL is required")

    root = Path(library_root) if library_root is not None else default_library_root()
    root.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    imported: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for item in items:
        url = _normalize_url(str(item.get("url") or item.get("source_url") or ""))
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        video_id = _video_id_from_url(url)
        material_id = _material_id(video_id)
        meta = _material_meta(
            item,
            material_id=material_id,
            video_id=video_id,
            url=url,
            product_id=product_id,
            source_keyword=source_keyword,
            crawl_time=now,
        )
        artifacts.validate_artifact("material_meta", meta)

        material_dir = root / material_id
        meta_path = material_dir / "material_meta.json"
        _atomic_write_json(meta_path, meta)
        imported.append(
            {
                "material_id": material_id,
                "video_id": video_id,
                "source_url": url,
                "material_meta_ref": meta_path.relative_to(root).as_posix(),
                "status": "raw",
                "product_id": product_id,
            }
        )

    if not imported:
        raise ValueError("no valid URLs found")

    index = upsert_library_index(root, imported, crawl_time=now)
    return {
        "library_root": root.as_posix(),
        "library_index_path": (root / LIBRARY_INDEX_NAME).as_posix(),
        "imported_count": len(imported),
        "items": imported,
        "library_index": index,
    }


def load_library_index(library_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    root = Path(library_root) if library_root is not None else default_library_root()
    path = root / LIBRARY_INDEX_NAME
    if not path.exists():
        return {"version": "2.0", "items": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifacts.validate_artifact("library_index", payload)
    return payload


def load_material_meta(material_id: str, library_root: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    safe_id = _safe_id(material_id)
    if safe_id != material_id:
        raise ValueError("invalid material_id")
    root = Path(library_root) if library_root is not None else default_library_root()
    path = root / material_id / "material_meta.json"
    if not path.exists():
        raise FileNotFoundError(f"material not found: {material_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    artifacts.validate_artifact("material_meta", payload)
    return payload


def update_material_meta(
    material_id: str,
    updates: dict[str, Any],
    library_root: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    root = Path(library_root) if library_root is not None else default_library_root()
    payload = load_material_meta(material_id, root)
    allowed = {
        "processing_status", "transcript_text", "ai_analysis_json", "local_video_path", "asset_intake",
            "source_mode", "local_cover_path",
            "video_title", "caption", "author_name", "author_url", "cover_url",
            "like_count", "comment_count", "share_count",
            "source_target_type", "discovery_relevance",
    }
    unknown = set(updates) - allowed
    if unknown:
        raise ValueError(f"unsupported material metadata fields: {', '.join(sorted(unknown))}")
    payload.update(updates)
    artifacts.validate_artifact("material_meta", payload)
    _atomic_write_json(root / material_id / "material_meta.json", payload)
    return payload


def delete_material(material_id: str, library_root: str | os.PathLike[str] | None = None) -> None:
    safe_id = _safe_id(material_id)
    if safe_id != material_id:
        raise ValueError("invalid material_id")
    root = (Path(library_root) if library_root is not None else default_library_root()).resolve()
    material_dir = (root / material_id).resolve()
    try:
        material_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("invalid material path") from exc
    if not material_dir.is_dir():
        raise FileNotFoundError(f"material not found: {material_id}")
    index = load_library_index(root)
    index["items"] = [item for item in index.get("items", []) if str(item.get("material_id")) != material_id]
    artifacts.validate_artifact("library_index", index)
    shutil.rmtree(material_dir)
    _atomic_write_json(root / LIBRARY_INDEX_NAME, index)


def upsert_library_index(
    library_root: Path,
    imported: list[dict[str, Any]],
    *,
    crawl_time: str,
) -> dict[str, Any]:
    index = load_library_index(library_root)
    by_id = {str(item["material_id"]): dict(item) for item in index.get("items", [])}
    for item in imported:
        material_id = str(item["material_id"])
        existing = by_id.get(material_id, {})
        tags = sorted(set(existing.get("tags") or []) | {"manual", "tiktok", str(item.get("product_id") or "")})
        by_id[material_id] = {
            "material_id": material_id,
            "material_meta_ref": str(item["material_meta_ref"]),
            "status": existing.get("status") or "raw",
            "fingerprint": _fingerprint(str(item["source_url"])),
            "thumbnail_path": existing.get("thumbnail_path") or "",
            "tags": [tag for tag in tags if tag],
            "created_at": existing.get("created_at") or crawl_time,
        }
    next_index = {"version": "2.0", "items": sorted(by_id.values(), key=lambda item: item["created_at"], reverse=True)}
    artifacts.validate_artifact("library_index", next_index)
    _atomic_write_json(library_root / LIBRARY_INDEX_NAME, next_index)
    return next_index


def default_library_root() -> Path:
    configured = os.environ.get("VAF_MATERIAL_LIBRARY_ROOT")
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return DATA_ROOT / "01_素材库" / "对标视频" / "manual_import"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items: list[Any] = []
    for key in ("items", "links", "urls"):
        value = payload.get(key)
        if isinstance(value, list):
            raw_items.extend(value)
    text = str(payload.get("links_text") or payload.get("text") or "")
    raw_items.extend(URL_RE.findall(text))

    items: list[dict[str, Any]] = []
    for raw in raw_items:
        if isinstance(raw, str):
            items.append({"url": raw})
        elif isinstance(raw, dict):
            items.append(dict(raw))
    return items


def extract_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return normalized collector inputs for provider-backed collectors."""
    return _extract_items(payload)


def _resolve_library_root(value: Any, context: ToolContext) -> Path:
    if value:
        path = Path(str(value))
        return path if path.is_absolute() else ROOT / path
    configured = context.env.get("VAF_MATERIAL_LIBRARY_ROOT") if context.env else None
    if configured:
        path = Path(configured)
        return path if path.is_absolute() else ROOT / path
    return default_library_root()


def _material_meta(
    item: dict[str, Any],
    *,
    material_id: str,
    video_id: str,
    url: str,
    product_id: str,
    source_keyword: str,
    crawl_time: str,
) -> dict[str, Any]:
    hashtags = item.get("hashtags") or _hashtags_from_caption(str(item.get("caption") or ""))
    if isinstance(hashtags, str):
        hashtags = [tag.strip("# ") for tag in hashtags.split(",") if tag.strip("# ")]
    meta = {
        "version": "2.0",
        "material_id": material_id,
        "product_id": product_id,
        "source_platform": "tiktok" if "tiktok" in url.lower() else "manual_link",
        "source_url": url,
        "video_url": str(item.get("video_url") or url),
        "video_id": video_id,
        "video_title": str(item.get("video_title") or item.get("title") or item.get("caption") or ""),
        "caption": str(item.get("caption") or ""),
        "author_name": str(item.get("author_name") or item.get("author") or ""),
        "author_url": str(item.get("author_url") or ""),
        "like_count": _int_value(item.get("like_count")),
        "comment_count": _int_value(item.get("comment_count")),
        "share_count": _int_value(item.get("share_count")),
        "collect_count": _int_value(item.get("collect_count")),
        "publish_time": item.get("publish_time"),
        "hashtags": [str(tag).strip("# ") for tag in hashtags if str(tag).strip("# ")],
        "music_title": str(item.get("music_title") or ""),
        "cover_url": str(item.get("cover_url") or ""),
        "source_keyword": source_keyword,
        "source_mode": str(item.get("source_mode") or "real"),
        "crawl_time": crawl_time,
        "processing_status": str(item.get("processing_status") or "raw"),
        "transcript_text": str(item.get("transcript_text") or ""),
        "ai_analysis_json": str(item.get("ai_analysis_json") or ""),
        "local_video_path": str(item.get("local_video_path") or ""),
        "local_cover_path": str(item.get("local_cover_path") or ""),
        "asset_intake": {
            "asset_type": "reference_only",
            "approval_status": "needs_review",
            "allowed_use": "Competitor structure, pacing, hook style, shot rhythm, and audience insight only.",
            "forbidden_use": "Do not copy competitor dialogue, claims, logos, product details, or visual identity.",
            "scene_tags": [],
            "claim_tags": [],
            "notes": str(
                item.get("asset_intake_notes")
                or "Manual channel-3 intake; metadata parsed from pasted link unless fields are supplied."
            ),
        },
    }
    return meta


def _normalize_url(url: str) -> str:
    cleaned = url.strip().strip("()[]{}<>\"'")
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    return cleaned


def _video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in ("video_id", "item_id", "id"):
        if query.get(key):
            return _safe_id(query[key][0])
    match = re.search(r"/video/(\d+)", parsed.path)
    if match:
        return match.group(1)
    parts = [part for part in parsed.path.split("/") if part]
    for part in reversed(parts):
        if part and part not in {"t", "v"}:
            return _safe_id(part)[:48]
    return _fingerprint(url)[:16]


def _material_id(video_id: str) -> str:
    return f"tt_{_safe_id(video_id)[:64]}"


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value).strip()).strip(".-")
    return safe or _fingerprint(str(value))[:16]


def _fingerprint(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def _hashtags_from_caption(caption: str) -> list[str]:
    return [tag.strip("#") for tag in re.findall(r"#[\w-]+", caption, flags=re.UNICODE)]


def _int_value(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)

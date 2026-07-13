from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

from libshared.paths import DATA_ROOT, ROOT


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
INDEX_VERSION = "2.0"
INDEX_NAME = "product_library_index.json"
PRODUCT_KEYWORDS = {
    "便携恒温杯": ("便携恒温杯", "恒温杯", "warming cup", "warmer"),
    "吸奶器": ("吸奶器", "panda-bubu-pro", "breast pump", "pump"),
    "奶瓶": ("奶瓶", "bottle"),
    "羊脂膏": ("羊脂膏", "lanolin"),
}
PRODUCT_LIST_ENV = "VAF_PRODUCT_LIBRARY_PRODUCTS"
PROHIBITED_MARKERS = ("竞品", "对比", "vs", "贝亲", "世喜", "momcozy", "baby brezza", "bololo")


def default_source_roots() -> list[Path]:
    return [
        ROOT / "data" / "01_素材库" / "产品资料",
        Path(r"C:\Users\bu\Documents\海外视频本地化工作流\01_素材库\产品资料"),
        Path(r"C:\Users\bu\Documents\海外视频本地化工作流\海外视频本地化MVP\产品资料"),
        Path(r"C:\Users\bu\Documents\海外视频本地化工作流\overseas-loc-mvp\knowledge\products"),
        Path(r"C:\Users\bu\Documents\海外视频本地化工作流\overseas-loc-mvp\knowledge\products\assets"),
        Path(r"\\DS223\obsidian知识库\shared-knowledge\products"),
    ]


def configured_source_roots(source_roots: Iterable[str | os.PathLike[str]] | None = None) -> list[Path]:
    if source_roots is not None:
        return [_resolve_path(root) for root in source_roots]
    env_value = os.environ.get("VAF_PRODUCT_LIBRARY_SOURCES", "")
    if env_value.strip():
        raw_roots = [part for chunk in env_value.split(";") for part in chunk.split(os.pathsep)]
        return [_resolve_path(part) for part in raw_roots if part.strip()]
    return default_source_roots()


def index_path(path: str | os.PathLike[str] | None = None) -> Path:
    if path is not None:
        return _resolve_path(path)
    env_value = os.environ.get("VAF_PRODUCT_LIBRARY_INDEX")
    if env_value:
        return _resolve_path(env_value)
    return DATA_ROOT / "01_素材库" / INDEX_NAME


def refresh_index(
    source_roots: Iterable[str | os.PathLike[str]] | None = None,
    *,
    path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    roots = configured_source_roots(source_roots)
    products: dict[str, dict[str, Any]] = {}
    source_status: list[dict[str, Any]] = []
    generated_at = utc_now()

    for root in roots:
        exists = root.exists()
        source_status.append({"path": root.as_posix(), "exists": exists})
        if not exists:
            continue
        _scan_root(root, products)

    for product in products.values():
        _finalize_product(product, source_status)

    payload = {
        "version": INDEX_VERSION,
        "generated_at": generated_at,
        "source_roots": source_status,
        "products": sorted(products.values(), key=lambda item: (not item["ready"], item["id"])),
    }
    target = index_path(path)
    _atomic_write_json(target, payload)
    return payload


def load_index(*, refresh_if_missing: bool = True, path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    target = index_path(path)
    if not target.exists():
        if refresh_if_missing:
            return refresh_index(path=target)
        return {"version": INDEX_VERSION, "generated_at": None, "source_roots": [], "products": []}
    return json.loads(target.read_text(encoding="utf-8"))


def get_product(product_id: str, *, refresh_if_missing: bool = True) -> dict[str, Any] | None:
    index = load_index(refresh_if_missing=refresh_if_missing)
    wanted = _normalize_product_id(product_id)
    for product in index.get("products", []):
        if _normalize_product_id(str(product.get("id"))) == wanted:
            return product
    return None


def resolve_seedance_source(product_id: str) -> str:
    product = get_product(product_id)
    if product and product.get("seedance_source"):
        return str(product["seedance_source"])
    fallback = ROOT / "data" / "01_素材库" / "产品资料" / "便携恒温杯" / "listing-0602-nw" / "主图" / "白底主图.png"
    return fallback.as_posix() if fallback.exists() else ""


def _scan_root(root: Path, products: dict[str, dict[str, Any]]) -> None:
    for markdown in _safe_glob(root, "*.md"):
        product_id = _infer_product_id(markdown, root)
        if product_id:
            _product(products, product_id)["docs"].append(_doc_payload(markdown, root))

    for child in _safe_iterdir(root):
        if not child.is_dir():
            continue
        if child.name.lower() == "assets":
            for product_dir in _safe_iterdir(child):
                if product_dir.is_dir():
                    product_id = _infer_product_id(product_dir, child) or product_dir.name
                    _scan_product_dir(product_dir, _product(products, product_id), root)
            continue
        product_id = _infer_product_id(child, root)
        if product_id:
            _scan_product_dir(child, _product(products, product_id), root)


def _scan_product_dir(product_dir: Path, product: dict[str, Any], source_root: Path) -> None:
    product["source_dirs"].append(product_dir.as_posix())
    for path in _safe_rglob(product_dir, "*"):
        if path.is_dir():
            continue
        suffix = path.suffix.casefold()
        if suffix == ".md":
            product["docs"].append(_doc_payload(path, source_root))
        elif suffix in IMAGE_SUFFIXES:
            product["assets"].append(_asset_payload(path, source_root, product["id"]))


def _product(products: dict[str, dict[str, Any]], product_id: str) -> dict[str, Any]:
    canonical = _canonical_product_id(product_id)
    if canonical not in products:
        products[canonical] = {
            "id": canonical,
            "label": canonical,
            "ready": False,
            "seedance_source": "",
            "docs": [],
            "assets": [],
            "counts": {},
            "issues": [],
            "source_dirs": [],
            "ds223_refreshed": False,
        }
    return products[canonical]


def _finalize_product(product: dict[str, Any], source_status: list[dict[str, Any]]) -> None:
    product["docs"] = _dedupe_by_path(product["docs"])
    product["assets"] = _dedupe_by_path(product["assets"])
    product["source_dirs"] = sorted(set(product["source_dirs"]))
    counts = Counter(asset["asset_type"] for asset in product["assets"])
    product["counts"] = dict(sorted(counts.items()))
    product["ds223_refreshed"] = any(_is_ds223_path(doc["source_path"]) for doc in product["docs"])

    white_hero = next((asset for asset in product["assets"] if asset.get("is_white_hero")), None)
    product["seedance_source"] = white_hero["source_path"] if white_hero else ""
    issues = []
    if not product["docs"]:
        issues.append(_issue("BLOCKED", "missing_product_doc", "缺少产品文档，不能从竞品或 AI 推断产品事实。"))
    if not white_hero:
        issues.append(_issue("BLOCKED", "missing_white_hero", "缺少白底主图，SeedDance 产品可见镜头不能放行。"))
    if counts.get("scene", 0) == 0:
        issues.append(_issue("WARNING", "missing_scene_image", "缺少场景图，后续只能走产品/手部/静物保守画面。"))
    if counts.get("usage_step", 0) == 0:
        issues.append(_issue("WARNING", "missing_usage_step", "缺少使用步骤图，演示镜头需要人工复核。"))
    if not any(_is_ds223_path(source["path"]) for source in source_status if source["exists"]):
        issues.append(_issue("WARNING", "ds223_not_available", "DS223 产品知识库未刷新，仅使用本地素材。"))
    product["issues"] = issues
    product["ready"] = not any(issue["severity"] == "BLOCKED" for issue in issues)


def _asset_payload(path: Path, source_root: Path, product_id: str) -> dict[str, Any]:
    asset_type, approval_status, allowed_use, forbidden_use = _classify_asset(path)
    return {
        "asset_id": _asset_id(product_id, path),
        "product": product_id,
        "source_path": path.as_posix(),
        "source_root": source_root.as_posix(),
        "asset_type": asset_type,
        "approval_status": approval_status,
        "allowed_use": allowed_use,
        "forbidden_use": forbidden_use,
        "scene_tags": _scene_tags(path),
        "person_profile": "",
        "claim_tags": [],
        "shot_roles": _shot_roles(asset_type),
        "notes": "",
        "is_white_hero": _is_white_hero(path),
    }


def _doc_payload(path: Path, source_root: Path) -> dict[str, Any]:
    return {
        "source_path": path.as_posix(),
        "source_root": source_root.as_posix(),
        "title": path.stem,
    }


def _classify_asset(path: Path) -> tuple[str, str, str, str]:
    text = _path_text(path)
    if any(marker.casefold() in text for marker in PROHIBITED_MARKERS):
        return (
            "prohibited",
            "prohibited",
            "Internal exclusion review only.",
            "Do not use in consumer-facing output or AI generation.",
        )
    if _is_white_hero(path):
        return (
            "product_identity",
            "approved",
            "Only SeedDance I2V product identity anchor for product-visible shots.",
            "Do not use as proof for unsupported claims.",
        )
    scene_markers = ("场景", "副图", "m端", "scene", "lifestyle")
    if (
        "倒出口" in text
        or "倒出" in text
        or "步骤" in text
        or "pour" in text
        or ("使用" in text and not any(marker in text for marker in scene_markers))
    ):
        return (
            "usage_step",
            "approved",
            "Prompt guidance for correct handling and usage flow.",
            "Do not override product identity from white-background hero.",
        )
    if any(marker in text for marker in scene_markers):
        return (
            "scene",
            "approved",
            "Prompt-only scene, props, and environment reference.",
            "Never use as SeedDance product identity source.",
        )
    if "细节" in text or "电池" in text or "加热" in text or "防水" in text or "防漏" in text or "结构" in text:
        return (
            "detail_proof",
            "approved",
            "Detail insert or exact visual support for approved wording.",
            "Do not convert into quantified efficacy or guarantee claims.",
        )
    if "主图" in text:
        return (
            "product_identity",
            "needs_review",
            "Possible product identity reference after human review.",
            "Do not use as white-background hero unless explicitly confirmed.",
        )
    return (
        "reference_only",
        "needs_review",
        "Composition or mood reference after human review.",
        "Do not use as product proof, claim support, or identity anchor.",
    )


def _infer_product_id(path: Path, root: Path) -> str | None:
    text = _path_text(path)
    for product_id, aliases in PRODUCT_KEYWORDS.items():
        if any(alias.casefold() in text for alias in aliases):
            return product_id
    configured = _configured_product_ids()
    candidate = path.stem if path.suffix else path.name
    if _normalize_text(candidate) in configured:
        return candidate
    if root.name.lower() == "assets":
        return path.name
    return None


def _canonical_product_id(product_id: str) -> str:
    text = product_id.casefold()
    for canonical, aliases in PRODUCT_KEYWORDS.items():
        if product_id == canonical or any(alias.casefold() in text for alias in aliases):
            return canonical
    return product_id


def _normalize_product_id(product_id: str) -> str:
    return _canonical_product_id(product_id).strip().casefold().replace(" ", "")


def _configured_product_ids() -> set[str]:
    env_value = os.environ.get(PRODUCT_LIST_ENV, "")
    parts = [part.strip() for chunk in env_value.split(";") for part in chunk.split(",")]
    return {_normalize_text(part) for part in parts if part}


def _normalize_text(value: str) -> str:
    return value.strip().casefold().replace(" ", "")


def _is_ds223_path(value: str) -> bool:
    normalized = value.replace("\\", "/").casefold()
    return normalized.startswith("//ds223/")


def _is_white_hero(path: Path) -> bool:
    return "白底主图" in _path_text(path) and path.suffix.casefold() in IMAGE_SUFFIXES


def _path_text(path: Path) -> str:
    return path.as_posix().casefold()


def _scene_tags(path: Path) -> list[str]:
    text = _path_text(path)
    tags = []
    for tag in ("night", "bedroom", "car", "travel", "airport", "office", "park", "restaurant", "场景"):
        if tag in text:
            tags.append(tag)
    return tags


def _shot_roles(asset_type: str) -> list[str]:
    return {
        "product_identity": ["product_visible", "identity_lock"],
        "usage_step": ["demo", "usage_flow"],
        "scene": ["scene_setup", "lifestyle_context"],
        "detail_proof": ["proof_insert", "detail"],
        "person": ["character_reference"],
    }.get(asset_type, ["reference"])


def _asset_id(product_id: str, path: Path) -> str:
    import hashlib

    digest = hashlib.sha1(path.as_posix().encode("utf-8")).hexdigest()[:10]
    safe_product = "".join(ch if ch.isalnum() else "_" for ch in product_id)
    return f"{safe_product}_{digest}"


def _issue(severity: str, code: str, message: str) -> dict[str, str]:
    return {"severity": severity, "code": code, "message": message}


def _dedupe_by_path(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    result = []
    for item in items:
        key = item.get("source_path")
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda item: item.get("source_path", ""))


def _safe_iterdir(path: Path) -> list[Path]:
    try:
        return list(path.iterdir())
    except OSError:
        return []


def _safe_glob(path: Path, pattern: str) -> list[Path]:
    try:
        return list(path.glob(pattern))
    except OSError:
        return []


def _safe_rglob(path: Path, pattern: str) -> list[Path]:
    try:
        return list(path.rglob(pattern))
    except OSError:
        return []


def _resolve_path(path: str | os.PathLike[str]) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp_path, path)

"""产品实拍/Listing 素材：垫图路径解析与交付项目注入。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from paths import PRODUCT_MATERIALS_DIR, WORKFLOW_ROOT

WHITE_HERO_CANDIDATES = (
    "主图/白底主图.png",
    "主图/白底主图.jpg",
    "主图/白底八背景.png",
    "主图/白底八背景.jpg",
)

USAGE_POUR_CANDIDATES = (
    "主图/倒出口参考.png",
    "主图/倒出口参考.jpg",
)

# 已废弃：白底主图缺失时不得用 KV/场景图兜底，生成应 BLOCKED
FALLBACK_HERO_CANDIDATES: tuple[str, ...] = ()


def _pick_clear_hero(root: Path) -> Path | None:
    """优先选高分辨率、产品主体清晰的垫图。"""
    preferred = root / "A+" / "KV.jpg"
    if preferred.is_file() and preferred.stat().st_size >= 400_000:
        return preferred
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        for path in sorted(sub.glob("*.jpg"), key=lambda p: p.stat().st_size, reverse=True):
            if any(k in path.name for k in ("白底", "主图", "KV")) and path.stat().st_size >= 250_000:
                return path
    return _pick_kv_hero(root)

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def product_listing_dir(product_id: str) -> Path:
    base = PRODUCT_MATERIALS_DIR / product_id
    for name in ("listing-0602-nw", "listing", "assets"):
        path = base / name
        if path.is_dir():
            return path
    return base / "listing-0602-nw"


def _pick_kv_hero(root: Path) -> Path | None:
    kv_files = sorted(root.rglob("KV.jpg"))
    for path in kv_files:
        if path.parent.name.upper().startswith("M"):
            return path
    return kv_files[0] if kv_files else None


def list_product_images(product_id: str) -> list[Path]:
    root = product_listing_dir(product_id)
    if not root.is_dir():
        return []
    return [
        p
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES and p.name != ".DS_Store"
    ]


def get_product_white_hero_image(product_id: str) -> Path | None:
    """白底主图：产品外观唯一锚点（SeedDance 默认垫图）。禁止用场景图/KV 替代。"""
    root = product_listing_dir(product_id)
    if not root.is_dir():
        return None
    for rel in WHITE_HERO_CANDIDATES:
        path = root / rel
        if path.is_file():
            return path
    main_dir = root / "主图"
    if main_dir.is_dir():
        for path in sorted(main_dir.glob("*")):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                name = path.name
                if "白底" in name and "倒出口" not in name:
                    return path
    return None


def get_product_usage_pour_image(product_id: str) -> Path | None:
    """倒出口参考：用法/倾倒演示锚点，不作产品身份垫图。"""
    root = product_listing_dir(product_id)
    if not root.is_dir():
        return None
    for rel in USAGE_POUR_CANDIDATES:
        path = root / rel
        if path.is_file():
            return path
    return None


def get_product_hero_image(product_id: str) -> Path | None:
    """兼容旧调用：等同于白底主图锚点。"""
    return get_product_white_hero_image(product_id)


def resolve_staged_seedance_source(project: Path | None) -> Path | None:
    """读取项目内已注入的白底主图垫图（忽略历史残留的 KV jpg 等多文件冲突）。"""
    if not project:
        return None
    inputs = project / "inputs"
    if not inputs.is_dir():
        return None
    meta_path = inputs / "seedance-source.meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            staged = str(meta.get("staged") or "").strip()
            if staged:
                path = inputs / staged
                if path.is_file():
                    return path
        except (json.JSONDecodeError, OSError):
            pass
    matches = [p for p in inputs.glob("seedance-source.*") if p.is_file() and p.suffix.lower() != ".json"]
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    for ext in (".png", ".webp", ".jpeg", ".jpg"):
        for path in matches:
            if path.suffix.lower() == ext:
                return path
    return sorted(matches)[0]


def stage_seedance_source_image(project: Path, product_id: str) -> Path | None:
    """将白底主图复制到交付项目 inputs/seedance-source.*，供 SeedDance 图生视频。"""
    hero = get_product_white_hero_image(product_id)
    if not hero:
        return None
    inputs = project / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    for old in inputs.glob("seedance-source.*"):
        if old.name == "seedance-source.meta.json":
            continue
        try:
            old.unlink()
        except OSError:
            pass
    target = inputs / f"seedance-source{hero.suffix.lower()}"
    shutil.copy2(hero, target)
    meta = {
        "product_id": product_id,
        "source": str(hero),
        "bytes": hero.stat().st_size,
        "staged": target.name,
        "rule": "白底主图唯一 I2V 垫图；禁止 KV/场景图/倒出口参考",
    }
    (inputs / "seedance-source.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target


def import_listing_folder(src: Path, product_id: str, *, dest_name: str = "listing-0602-nw") -> Path:
    """从外部目录导入 Listing 素材到产品资料库。"""
    dest = PRODUCT_MATERIALS_DIR / product_id / dest_name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    mirror = WORKFLOW_ROOT / "overseas-loc-mvp" / "knowledge" / "products" / "assets" / product_id / dest_name
    mirror.parent.mkdir(parents=True, exist_ok=True)
    if mirror.exists():
        shutil.rmtree(mirror)
    shutil.copytree(dest, mirror)
    return dest
